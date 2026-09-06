"""The two invariants from PRD 12: the last unit, and idempotent transitions."""

from __future__ import annotations

from datetime import date

from app.core.service import (
    ConfirmOutcome,
    claim_unit,
    confirm_or_waitlist,
    create_request,
    ensure_donor_request,
    mark_completed,
    release_unit,
    transition,
    waitlisted_donors,
)
from app.enums import BloodGroup, DonorRequestStatus, RequestStatus, Sex
from app.models import BloodRequest
from tests.conftest import make_donor, make_request


async def _setup(session, *, units=1, donors=2):
    request = make_request(units=units)
    session.add(request)
    for i in range(1, donors + 1):
        session.add(make_donor(i))
    await session.flush()

    links = []
    for i in range(1, donors + 1):
        link, _ = await ensure_donor_request(session, request.id, i)
        await transition(
            session, link, DonorRequestStatus.SCREENING, expected=(DonorRequestStatus.NOTIFIED,)
        )
        links.append(link)
    return request, links


# --------------------------------------------------------------------------------------
# The last unit
# --------------------------------------------------------------------------------------


async def test_two_donors_racing_for_one_unit_resolve_to_one_confirmation(session):
    request, (first, second) = await _setup(session, units=1, donors=2)

    a = await confirm_or_waitlist(session, first, request)
    b = await confirm_or_waitlist(session, second, request)

    assert a.outcome is ConfirmOutcome.CONFIRMED
    assert b.outcome is ConfirmOutcome.WAITLISTED
    await session.refresh(request)
    assert request.confirmed_count == 1
    assert request.status == RequestStatus.FILLED


async def test_claim_stops_exactly_at_units_needed(session):
    request, links = await _setup(session, units=2, donors=4)
    outcomes = [(await confirm_or_waitlist(session, link, request)).outcome for link in links]

    assert outcomes.count(ConfirmOutcome.CONFIRMED) == 2
    assert outcomes.count(ConfirmOutcome.WAITLISTED) == 2
    await session.refresh(request)
    assert request.confirmed_count == 2


async def test_claim_unit_refuses_past_the_requirement(session):
    request, _ = await _setup(session, units=1, donors=1)
    assert await claim_unit(session, request.id) is True
    assert await claim_unit(session, request.id) is False


async def test_claim_unit_refuses_on_a_closed_request(session):
    request, _ = await _setup(session, units=5, donors=1)
    request.status = RequestStatus.CANCELLED
    await session.flush()
    assert await claim_unit(session, request.id) is False


async def test_release_returns_the_unit(session):
    request, (link, _) = await _setup(session, units=1, donors=2)
    await confirm_or_waitlist(session, link, request)
    await release_unit(session, request.id)
    await session.refresh(request)
    assert request.confirmed_count == 0


async def test_filling_the_request_marks_the_filling_confirmation(session):
    request, (first, second) = await _setup(session, units=2, donors=2)
    assert (await confirm_or_waitlist(session, first, request)).just_filled is False
    assert (await confirm_or_waitlist(session, second, request)).just_filled is True


async def test_waitlist_is_ordered_oldest_first(session):
    request, links = await _setup(session, units=1, donors=3)
    for link in links:
        await confirm_or_waitlist(session, link, request)

    waiting = await waitlisted_donors(session, request.id)
    assert [w.donor_id for w in waiting] == [2, 3]


# --------------------------------------------------------------------------------------
# Idempotency: Telegram redelivers taps
# --------------------------------------------------------------------------------------


async def test_replayed_confirmation_does_not_consume_a_second_unit(session):
    request, (link, _) = await _setup(session, units=2, donors=2)

    first = await confirm_or_waitlist(session, link, request)
    replay = await confirm_or_waitlist(session, link, request)

    assert first.outcome is ConfirmOutcome.CONFIRMED
    assert replay.outcome is ConfirmOutcome.ALREADY_HANDLED
    await session.refresh(request)
    assert request.confirmed_count == 1


async def test_transition_is_a_no_op_from_an_unexpected_state(session):
    request, (link, _) = await _setup(session, units=1, donors=2)

    assert await transition(
        session, link, DonorRequestStatus.DECLINED, expected=(DonorRequestStatus.SCREENING,)
    )
    assert not await transition(
        session, link, DonorRequestStatus.ACCEPTED, expected=(DonorRequestStatus.NOTIFIED,)
    )
    assert link.status == DonorRequestStatus.DECLINED


async def test_ensure_donor_request_is_idempotent(session):
    request = make_request()
    session.add(request)
    session.add(make_donor(1))
    await session.flush()

    first, created_first = await ensure_donor_request(session, request.id, 1)
    second, created_second = await ensure_donor_request(session, request.id, 1)

    assert created_first is True
    assert created_second is False
    assert first.id == second.id


# --------------------------------------------------------------------------------------
# Request intake
# --------------------------------------------------------------------------------------


async def _create(session, external_id="ext-1", bank="demo_bank"):
    return await create_request(
        session,
        blood_bank_id=bank,
        external_id=external_id,
        blood_group=BloodGroup.O_POS,
        units_needed=2,
        hospital_name="General Hospital",
        hospital_address="MG Road",
        district="Ernakulam",
        city="Kochi",
        needed_by=make_request().needed_by,
    )


async def test_repeating_an_external_id_returns_the_original_request(session):
    first = await _create(session)
    second = await _create(session)

    assert first.created is True
    assert second.created is False
    assert first.request.id == second.request.id


async def test_different_banks_may_reuse_an_external_id(session):
    first = await _create(session, bank="demo_bank")
    second = await _create(session, bank="other_bank")
    assert first.request.id != second.request.id


async def test_public_ids_are_short_enough_for_a_deep_link(session):
    result = await _create(session)
    assert len(f"req_{result.request.public_id}") <= 64


# --------------------------------------------------------------------------------------
# Completion
# --------------------------------------------------------------------------------------


async def test_completion_updates_cooldown_and_is_idempotent(session):
    request, (link, _) = await _setup(session, units=2, donors=2)
    await confirm_or_waitlist(session, link, request)

    donated_on = date(2026, 3, 1)
    first = await mark_completed(session, link, donated_on)
    replay = await mark_completed(session, link, donated_on)

    assert first.recorded is True
    assert replay.recorded is False
    assert first.donor.last_donation_date == donated_on
    assert first.next_eligible == date(2026, 5, 30)  # +90 days, male
    await session.refresh(request)
    assert request.completed_count == 1


async def test_completion_verifies_the_blood_group_on_file(session):
    request, (link, _) = await _setup(session, units=1, donors=2)
    await confirm_or_waitlist(session, link, request)
    result = await mark_completed(session, link, date.today())
    assert result.donor.blood_group_verified is True


async def test_completion_uses_the_female_cooldown(session):
    request = make_request(units=1)
    session.add(request)
    donor = make_donor(1, sex=Sex.FEMALE)
    session.add(donor)
    await session.flush()

    link, _ = await ensure_donor_request(session, request.id, 1)
    await transition(
        session, link, DonorRequestStatus.SCREENING, expected=(DonorRequestStatus.NOTIFIED,)
    )
    await confirm_or_waitlist(session, link, request)

    result = await mark_completed(session, link, date(2026, 3, 1))
    assert result.next_eligible == date(2026, 6, 29)  # +120 days


async def test_units_remaining_never_goes_negative(session):
    request = BloodRequest(
        public_id="X1",
        blood_bank_id="demo_bank",
        external_id="e",
        blood_group=BloodGroup.O_POS,
        units_needed=1,
        confirmed_count=3,
        hospital_name="H",
        hospital_address="A",
        district="Ernakulam",
        needed_by=make_request().needed_by,
    )
    assert request.units_remaining == 0
