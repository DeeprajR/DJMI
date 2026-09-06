"""The shared-database contract with the blood bank, and the admin cards.

The two ``public`` tables are created in the test database from the bot's Core
definitions -- in production the bank's migrations own them.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest_asyncio
from sqlalchemy import select, update

from app.bot.admin import notify_admins, refresh_admin_cards, share_text
from app.core.service import confirm_or_waitlist, transition
from app.db import engine
from app.distribution import dispatch_new_request, run_wave
from app.enums import DonorRequestStatus, RequestStatus
from app.integration import demand as bank
from app.models import Admin, AdminCard, BloodRequest, Donor, DonorRequest
from tests.conftest import make_donor, make_request


@pytest_asyncio.fixture(autouse=True)
async def shared_tables(session):
    async with engine.begin() as conn:
        await conn.run_sync(bank.shared.drop_all)
        await conn.run_sync(bank.shared.create_all)
    yield


async def insert_demand(session, **overrides) -> str:
    demand_id = str(uuid.uuid4())
    row = {
        "id": demand_id,
        "trigger": "request_shortfall",
        "blood_group": "O+",
        "product": "whole_blood",
        "units": 2,
        "date_needed": date.today() + timedelta(days=1),
        "hospital_name": "Medical College Hospital",
        "hospital_address": "Blood Bank, 2nd floor",
        "district": "Ernakulam",
        "city": "Kochi",
        "status": "open",
        "confirmed_units": 0,
        "waitlisted_units": 0,
        "completed_units": 0,
        "notified_donors": 0,
    }
    row.update(overrides)
    await session.execute(bank.donor_demand.insert().values(**row))
    await session.commit()
    return demand_id


async def read_demand(session, demand_id: str) -> dict:
    row = (
        (
            await session.execute(
                select(bank.donor_demand).where(bank.donor_demand.c.id == demand_id)
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


# --------------------------------------------------------------------------------------
# Bank -> bot
# --------------------------------------------------------------------------------------


async def test_an_open_demand_becomes_a_request_and_notifies_donors(session, bot):
    session.add(make_donor(1))
    session.add(make_donor(2))
    await session.commit()
    demand_id = await insert_demand(session, units=1)

    imported = await bank.import_open_demands(bot, session)
    await session.commit()

    assert imported == 1
    request = await session.scalar(select(BloodRequest).where(BloodRequest.demand_id == demand_id))
    assert request is not None
    assert request.blood_group == "O+" and request.units_needed == 1
    assert request.hospital_name == "Medical College Hospital"
    assert [m["chat_id"] for m in bot.sent] == [1, 2]

    row = await read_demand(session, demand_id)
    assert row["bot_public_id"] == request.public_id
    assert row["notified_donors"] == 2
    assert row["status"] == "open"


async def test_a_demand_is_imported_only_once(session, bot):
    session.add(make_donor(1))
    await session.commit()
    demand_id = await insert_demand(session)

    assert await bank.import_open_demands(bot, session) == 1
    await session.commit()
    assert await bank.import_open_demands(bot, session) == 0

    count = len((await session.scalars(select(BloodRequest))).all())
    assert count == 1
    assert (await read_demand(session, demand_id))["bot_public_id"] is not None


async def test_needed_by_is_the_end_of_the_bank_day(session, bot):
    day = date.today() + timedelta(days=2)
    demand_id = await insert_demand(session, date_needed=day)
    await bank.import_open_demands(bot, session)

    request = await session.scalar(select(BloodRequest).where(BloodRequest.demand_id == demand_id))
    needed = bank.needed_by_from_date(day)
    assert request.needed_by.replace(tzinfo=None) == needed.replace(tzinfo=None)


async def test_the_card_shows_a_day_for_bank_demand(session, bot):
    session.add(make_donor(1))
    await session.commit()
    await insert_demand(session)
    await bank.import_open_demands(bot, session)

    assert "Needed by" in bot.sent[0]["text"]
    assert "Before" not in bot.sent[0]["text"]


async def test_a_bank_cancellation_closes_the_bot_request(session, bot):
    session.add(make_donor(1))
    await session.commit()
    demand_id = await insert_demand(session)
    await bank.import_open_demands(bot, session)
    await session.commit()

    await session.execute(
        update(bank.donor_demand)
        .where(bank.donor_demand.c.id == demand_id)
        .values(status="cancelled")
    )
    closed = await bank.apply_bank_cancellations(bot, session)

    assert closed == 1
    request = await session.scalar(select(BloodRequest).where(BloodRequest.demand_id == demand_id))
    assert request.status == RequestStatus.CANCELLED
    assert len(bot.edited) == 1  # the donor's card lost its buttons


# --------------------------------------------------------------------------------------
# Bot -> bank
# --------------------------------------------------------------------------------------


async def _confirm(session, request, donor_id: int):
    link = await session.scalar(
        select(DonorRequest).where(
            DonorRequest.request_id == request.id, DonorRequest.donor_id == donor_id
        )
    )
    await transition(
        session, link, DonorRequestStatus.SCREENING, expected=(DonorRequestStatus.NOTIFIED,)
    )
    return await confirm_or_waitlist(session, link, request)


async def test_a_confirmation_appears_on_the_bank_roster(session, bot):
    session.add(make_donor(1))
    await session.commit()
    demand_id = await insert_demand(session, units=1)
    await bank.import_open_demands(bot, session)
    request = await session.scalar(select(BloodRequest).where(BloodRequest.demand_id == demand_id))

    await _confirm(session, request, 1)
    donor = await session.get(Donor, 1)
    await bank.record_confirmation(session, request, donor)
    await bank.report_progress(session, request)

    roster = (await session.execute(select(bank.donor_demand_confirmations))).mappings().all()
    assert len(roster) == 1
    assert roster[0]["telegram_user_id"] == 1
    assert roster[0]["donor_phone"] == donor.phone
    assert roster[0]["status"] == "confirmed"

    row = await read_demand(session, demand_id)
    assert row["confirmed_units"] == 1
    assert row["status"] == "fulfilled"


async def test_recording_the_same_confirmation_twice_is_harmless(session, bot):
    session.add(make_donor(1))
    await session.commit()
    demand_id = await insert_demand(session, units=1)
    await bank.import_open_demands(bot, session)
    request = await session.scalar(select(BloodRequest).where(BloodRequest.demand_id == demand_id))
    donor = await session.get(Donor, 1)

    await bank.record_confirmation(session, request, donor)
    await bank.record_confirmation(session, request, donor)

    roster = (await session.execute(select(bank.donor_demand_confirmations))).mappings().all()
    assert len(roster) == 1


async def test_progress_reports_waitlist_and_notified_counts(session, bot):
    for i in range(1, 4):
        session.add(make_donor(i))
    await session.commit()
    demand_id = await insert_demand(session, units=1)
    await bank.import_open_demands(bot, session)
    request = await session.scalar(select(BloodRequest).where(BloodRequest.demand_id == demand_id))

    await _confirm(session, request, 1)
    await _confirm(session, request, 2)
    await bank.report_progress(session, request)

    row = await read_demand(session, demand_id)
    assert row["confirmed_units"] == 1
    assert row["waitlisted_units"] == 1
    assert row["notified_donors"] == 3


# --------------------------------------------------------------------------------------
# The counter marks a donation
# --------------------------------------------------------------------------------------


async def test_a_completed_mark_updates_the_cooldown_and_thanks_the_donor(session, bot):
    session.add(make_donor(1))
    await session.commit()
    demand_id = await insert_demand(session, units=1)
    await bank.import_open_demands(bot, session)
    request = await session.scalar(select(BloodRequest).where(BloodRequest.demand_id == demand_id))
    await _confirm(session, request, 1)
    await bank.record_confirmation(session, request, await session.get(Donor, 1))
    await session.commit()
    bot.sent.clear()

    await session.execute(
        update(bank.donor_demand_confirmations).values(
            status="completed", donated_at=date(2026, 9, 7), bag_rfid_tag="BAG-0001"
        )
    )
    handled = await bank.acknowledge_counter_updates(bot, session)

    assert handled == 1
    donor = await session.get(Donor, 1)
    await session.refresh(donor)
    assert donor.last_donation_date == date(2026, 9, 7)
    assert "06 Dec 2026" in bot.sent[-1]["text"]  # +90 days, male
    row = (await session.execute(select(bank.donor_demand_confirmations))).mappings().one()
    assert row["bot_acknowledged_at"] is not None
    demand = await read_demand(session, demand_id)
    assert demand["completed_units"] == 1
    assert demand["status"] == "completed"


async def test_a_mark_is_acknowledged_only_once(session, bot):
    session.add(make_donor(1))
    await session.commit()
    demand_id = await insert_demand(session, units=1)
    await bank.import_open_demands(bot, session)
    request = await session.scalar(select(BloodRequest).where(BloodRequest.demand_id == demand_id))
    await _confirm(session, request, 1)
    await bank.record_confirmation(session, request, await session.get(Donor, 1))
    await session.execute(
        update(bank.donor_demand_confirmations).values(status="completed", donated_at=date.today())
    )

    assert await bank.acknowledge_counter_updates(bot, session) == 1
    assert await bank.acknowledge_counter_updates(bot, session) == 0


async def test_a_cancelled_mark_releases_the_unit(session, bot):
    session.add(make_donor(1))
    await session.commit()
    demand_id = await insert_demand(session, units=2)
    await bank.import_open_demands(bot, session)
    request = await session.scalar(select(BloodRequest).where(BloodRequest.demand_id == demand_id))
    await _confirm(session, request, 1)
    await bank.record_confirmation(session, request, await session.get(Donor, 1))
    await session.execute(update(bank.donor_demand_confirmations).values(status="cancelled"))

    await bank.acknowledge_counter_updates(bot, session)

    await session.refresh(request)
    assert request.confirmed_count == 0
    link = await session.scalar(select(DonorRequest).where(DonorRequest.donor_id == 1))
    assert link.status == DonorRequestStatus.CANCELLED


# --------------------------------------------------------------------------------------
# Volunteer admins (P0-12)
# --------------------------------------------------------------------------------------


async def test_admins_get_a_card_and_a_forwardable_message(session, bot):
    session.add(Admin(telegram_user_id=9001, name="Anu", district="Ernakulam"))
    session.add(Admin(telegram_user_id=9002, name="Everywhere", district=None))
    session.add(Admin(telegram_user_id=9003, name="Kollam", district="Kollam"))
    session.add(Admin(telegram_user_id=9004, name="Retired", district=None, active=False))
    request = make_request(units=2)
    session.add(request)
    await session.flush()

    reached = await notify_admins(bot, session, request)

    assert reached == 2
    recipients = [m["chat_id"] for m in bot.sent]
    assert recipients == [9001, 9001, 9002, 9002]  # card + share, per admin
    card, share = bot.sent[0]["text"], bot.sent[1]["text"]
    assert "0/2 confirmed" in card
    assert f"start=req_{request.public_id}" in share
    assert "patient" not in share.lower() or "No patient details" in share
    cards = (await session.scalars(select(AdminCard))).all()
    assert {c.admin_id for c in cards} == {9001, 9002}


async def test_admins_are_not_notified_twice_for_one_request(session, bot):
    session.add(Admin(telegram_user_id=9001, district=None))
    request = make_request(units=2)
    session.add(request)
    await session.flush()

    await notify_admins(bot, session, request)
    await notify_admins(bot, session, request)

    assert len(bot.sent) == 2


async def test_the_admin_card_is_edited_as_confirmations_arrive(session, bot):
    session.add(Admin(telegram_user_id=9001, district=None))
    for i in range(1, 3):
        session.add(make_donor(i))
    request = make_request(units=2)
    session.add(request)
    await session.flush()
    await dispatch_new_request(bot, session, request)  # donors, admins, and progress
    edits_before = len(bot.edited)

    await _confirm(session, request, 1)
    await refresh_admin_cards(bot, session, request)

    assert len(bot.edited) == edits_before + 1
    assert "1/2 confirmed" in bot.edited[-1]["text"]


async def test_the_admin_card_closes_out_when_filled(session, bot):
    session.add(Admin(telegram_user_id=9001, district=None))
    session.add(make_donor(1))
    request = make_request(units=1)
    session.add(request)
    await session.flush()
    await dispatch_new_request(bot, session, request)

    await _confirm(session, request, 1)
    await refresh_admin_cards(bot, session, request)

    assert "stop sharing" in bot.edited[-1]["text"].lower()


def test_the_share_text_carries_everything_an_outsider_needs():
    request = make_request(units=3, blood_group="AB-")
    text = share_text(request, "en")
    for needle in ("AB-", "3", "General Hospital", "MG Road", "Ernakulam", "t.me/"):
        assert needle in text


async def test_a_wave_reports_progress_to_the_bank(session, bot):
    session.add(make_donor(1))
    await session.commit()
    demand_id = await insert_demand(session, units=5)
    await bank.import_open_demands(bot, session)
    request = await session.scalar(select(BloodRequest).where(BloodRequest.demand_id == demand_id))
    session.add(make_donor(2))
    await session.flush()

    await run_wave(bot, session, request)

    assert (await read_demand(session, demand_id))["notified_donors"] == 2
