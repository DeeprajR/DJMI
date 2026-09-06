"""Wave fan-out (PRD 7.5, P0-5).

The acceptance criterion is negative: once the units are met, the next wave timer must
notify nobody.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.service import (
    confirm_or_waitlist,
    ensure_donor_request,
    transition,
)
from app.distribution import expire_request, run_wave, tick
from app.enums import DonorRequestStatus, RequestStatus
from app.models import DonorRequest
from tests.conftest import make_donor, make_request


async def _seed(session, donor_count: int, **request_kwargs):
    request = make_request(**request_kwargs)
    session.add(request)
    for i in range(1, donor_count + 1):
        session.add(make_donor(i))
    await session.flush()
    return request


async def test_first_wave_is_capped_and_the_second_takes_the_rest(session, bot):
    request = await _seed(session, 5, units=5)

    first = await run_wave(bot, session, request)
    assert first == 3  # WAVE_SIZE
    assert request.wave_index == 1

    second = await run_wave(bot, session, request)
    assert second == 2
    assert sorted(m["chat_id"] for m in bot.sent) == [1, 2, 3, 4, 5]


async def test_a_donor_is_never_notified_twice_for_one_request(session, bot):
    request = await _seed(session, 3, units=5)
    await run_wave(bot, session, request)
    await run_wave(bot, session, request)

    links = (await session.scalars(select(DonorRequest))).all()
    assert len(links) == 3
    assert len(bot.sent) == 3


async def test_no_further_donors_are_notified_once_units_are_met(session, bot):
    request = await _seed(session, 5, units=1)
    await run_wave(bot, session, request)
    sent_after_first_wave = len(bot.sent)

    # The first donor passes screening and takes the only unit.
    link = await session.scalar(select(DonorRequest).where(DonorRequest.donor_id == 1))
    await transition(
        session, link, DonorRequestStatus.SCREENING, expected=(DonorRequestStatus.NOTIFIED,)
    )
    await confirm_or_waitlist(session, link, request)
    assert request.status == RequestStatus.FILLED

    # The escalation timer fires anyway; nobody new hears about it.
    assert await run_wave(bot, session, request) == 0
    assert len(bot.sent) == sent_after_first_wave


async def test_a_wave_schedules_the_next_escalation(session, bot):
    request = await _seed(session, 5, units=5)
    await run_wave(bot, session, request)

    assert request.next_wave_at is not None
    assert request.next_wave_at > datetime.now(UTC)


async def test_escalation_is_never_scheduled_past_the_deadline(session, bot):
    """WAVE_INTERVAL is 30 minutes; a request due in 10 gets no further wave."""
    request = await _seed(session, 5, units=5)
    request.needed_by = datetime.now(UTC) + timedelta(minutes=10)
    await session.flush()

    await run_wave(bot, session, request)
    assert request.next_wave_at is None


async def test_a_past_deadline_expires_the_request_and_closes_cards(session, bot):
    request = await _seed(session, 2, units=5)
    await run_wave(bot, session, request)

    request.needed_by = datetime.now(UTC) - timedelta(minutes=1)
    await session.flush()
    await expire_request(bot, session, request)

    assert request.status == RequestStatus.EXPIRED
    assert len(bot.edited) == 2
    assert "expired" in bot.edited[0]["text"].lower()


async def test_tick_escalates_only_requests_that_are_due(session, bot):
    due = await _seed(session, 5, units=5, public_id="DUEREQ01", external_id="due")
    later = make_request(public_id="LATERQ01", external_id="later", units=5)
    session.add(later)
    await session.flush()

    due.next_wave_at = datetime.now(UTC) - timedelta(minutes=1)
    later.next_wave_at = datetime.now(UTC) + timedelta(hours=1)
    await session.commit()

    await tick(bot)

    await session.refresh(due)
    await session.refresh(later)
    assert due.wave_index == 1
    assert later.wave_index == 0


async def test_tick_expires_requests_whose_deadline_has_passed(session, bot):
    request = await _seed(session, 1, units=5)
    request.needed_by = datetime.now(UTC) - timedelta(minutes=5)
    await session.commit()

    await tick(bot)

    await session.refresh(request)
    assert request.status == RequestStatus.EXPIRED


async def test_a_blocked_donor_is_opted_out_and_left_free_for_a_later_wave(session, bot):
    request = await _seed(session, 1, units=5)

    async def refuse(*args, **kwargs):
        from aiogram.exceptions import TelegramForbiddenError

        raise TelegramForbiddenError(method=None, message="bot was blocked by the user")

    bot.send_message = refuse
    reached = await run_wave(bot, session, request)

    assert reached == 0
    donor = (await session.scalars(select(DonorRequest))).all()
    assert donor == []  # no dangling link row


async def test_a_donor_who_already_responded_is_not_re_notified(session, bot):
    request = await _seed(session, 3, units=5)
    link, _ = await ensure_donor_request(session, request.id, 2)
    await transition(
        session, link, DonorRequestStatus.DECLINED, expected=(DonorRequestStatus.NOTIFIED,)
    )

    await run_wave(bot, session, request)
    assert sorted(m["chat_id"] for m in bot.sent) == [1, 3]
