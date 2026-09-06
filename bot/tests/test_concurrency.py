"""Multi-user isolation.

aiogram runs every update as its own asyncio task (``handle_as_tasks=True``), and
``DbSessionMiddleware`` gives each one its own transaction. These tests reproduce that
shape faithfully: each simulated tap opens its **own** ``session_scope``, and taps from
different donors are interleaved with ``asyncio.gather`` rather than run in order.

That matters because the sequential tests elsewhere share one session, which would hide
both cross-talk between donors and any transaction-level race.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from app.bot.handlers.requests import accept, answer_question
from app.bot.states import Onboarding, QuizCB, ReqCB
from app.core import questionnaire as quiz
from app.core.service import get_donor_request, get_request_by_public_id
from app.db import session_scope
from app.distribution import run_wave
from app.enums import DonorRequestStatus, RequestStatus
from app.models import Donor, DonorRequest
from tests.conftest import StubQuery, make_donor, make_request


async def _open_request(session, bot, *, units: int, donors: int) -> str:
    """An open request with every donor already holding a card.

    Waves are capped at ``WAVE_SIZE`` (3 in the test environment), so this escalates
    until the pool is exhausted -- otherwise a test that says "8 donors race" would
    quietly only ever notify 3 of them.
    """
    request = make_request(units=units)
    session.add(request)
    for i in range(1, donors + 1):
        session.add(make_donor(i))
    await session.flush()

    while await run_wave(bot, session, request):
        pass

    await session.commit()
    return request.public_id


async def _tap_accept(bot, public_id: str, donor_id: int) -> StubQuery:
    """One Accept tap, in its own transaction -- exactly what the middleware does."""
    query = StubQuery(bot, donor_id)
    async with session_scope() as session:
        donor = await session.get(Donor, donor_id)
        await accept(query, ReqCB(action="acc", pid=public_id), session, donor)
    return query


async def _tap_answer(bot, public_id: str, donor_id: int, index: int, answer: bool) -> StubQuery:
    query = StubQuery(bot, donor_id)
    async with session_scope() as session:
        donor = await session.get(Donor, donor_id)
        await answer_question(
            query, QuizCB(pid=public_id, idx=index, ans=int(answer)), session, donor
        )
    return query


async def _screen_to_completion(bot, public_id: str, donor_id: int) -> list[StubQuery]:
    """Walk one donor through the whole questionnaire, one transaction per tap."""
    queries = []
    index = 0
    while (question := quiz.question_at("M", index)) is not None:
        queries.append(
            await _tap_answer(bot, public_id, donor_id, index, not question.disqualifying_answer)
        )
        index += 1
    return queries


# --------------------------------------------------------------------------------------
# The last unit, under real concurrency
# --------------------------------------------------------------------------------------


async def test_two_donors_racing_for_one_unit_in_separate_transactions(session, bot):
    """The guard has to hold when the two flows genuinely interleave, not just in order."""
    public_id = await _open_request(session, bot, units=1, donors=2)

    await asyncio.gather(_tap_accept(bot, public_id, 1), _tap_accept(bot, public_id, 2))
    await asyncio.gather(
        _screen_to_completion(bot, public_id, 1),
        _screen_to_completion(bot, public_id, 2),
    )

    async with session_scope() as s:
        request = await get_request_by_public_id(s, public_id)
        statuses = {
            link.donor_id: link.status
            for link in await s.scalars(
                select(DonorRequest).where(DonorRequest.request_id == request.id)
            )
        }

    assert sorted(statuses.values()) == [
        DonorRequestStatus.CONFIRMED,
        DonorRequestStatus.REQUEST_FILLED,
    ]
    assert request.confirmed_count == 1
    assert request.status == RequestStatus.FILLED


async def test_eight_donors_two_units_awards_exactly_two(session, bot):
    public_id = await _open_request(session, bot, units=2, donors=8)

    await asyncio.gather(*(_tap_accept(bot, public_id, i) for i in range(1, 9)))
    await asyncio.gather(*(_screen_to_completion(bot, public_id, i) for i in range(1, 9)))

    async with session_scope() as s:
        request = await get_request_by_public_id(s, public_id)
        links = list(
            await s.scalars(select(DonorRequest).where(DonorRequest.request_id == request.id))
        )

    confirmed = [link for link in links if link.status == DonorRequestStatus.CONFIRMED]
    waitlisted = [link for link in links if link.status == DonorRequestStatus.REQUEST_FILLED]

    assert len(confirmed) == 2, "over- or under-booked the requirement"
    assert len(waitlisted) == 6
    assert request.confirmed_count == 2
    # Nobody is confirmed twice, and every donor ended somewhere.
    assert len({link.donor_id for link in links}) == 8


# --------------------------------------------------------------------------------------
# Donors do not see each other's answers
# --------------------------------------------------------------------------------------


async def test_interleaved_questionnaires_stay_on_their_own_rows(session, bot):
    """Three donors answering at the same time must not share progress."""
    public_id = await _open_request(session, bot, units=5, donors=3)
    await asyncio.gather(*(_tap_accept(bot, public_id, i) for i in range(1, 4)))

    # Advance each donor a different distance, interleaved.
    await asyncio.gather(
        _tap_answer(bot, public_id, 1, 0, True),
        _tap_answer(bot, public_id, 2, 0, True),
        _tap_answer(bot, public_id, 3, 0, True),
    )
    await asyncio.gather(
        _tap_answer(bot, public_id, 1, 1, True),
        _tap_answer(bot, public_id, 2, 1, True),
    )
    await _tap_answer(bot, public_id, 1, 2, False)

    async with session_scope() as s:
        request = await get_request_by_public_id(s, public_id)
        answers = {
            link.donor_id: len(link.answers or {})
            for link in await s.scalars(
                select(DonorRequest).where(DonorRequest.request_id == request.id)
            )
        }

    assert answers == {1: 3, 2: 2, 3: 1}


async def test_one_donor_failing_screening_does_not_affect_the_others(session, bot):
    public_id = await _open_request(session, bot, units=5, donors=3)
    await asyncio.gather(*(_tap_accept(bot, public_id, i) for i in range(1, 4)))

    # Donor 2 answers "yes" to the recent-illness question (index 2) and is eliminated.
    await asyncio.gather(
        _screen_to_completion(bot, public_id, 1),
        _tap_answer(bot, public_id, 2, 0, True),
        _screen_to_completion(bot, public_id, 3),
    )
    await _tap_answer(bot, public_id, 2, 1, True)
    await _tap_answer(bot, public_id, 2, 2, True)  # disqualifying

    async with session_scope() as s:
        request = await get_request_by_public_id(s, public_id)
        statuses = {
            link.donor_id: link.status
            for link in await s.scalars(
                select(DonorRequest).where(DonorRequest.request_id == request.id)
            )
        }
        donors = {d.telegram_user_id: d for d in await s.scalars(select(Donor))}

    assert statuses[1] == DonorRequestStatus.CONFIRMED
    assert statuses[2] == DonorRequestStatus.ELIMINATED
    assert statuses[3] == DonorRequestStatus.CONFIRMED
    assert request.confirmed_count == 2
    # The eliminated donor's own profile is untouched, and so is everyone else's.
    assert all(d.is_registered and not d.opted_out for d in donors.values())


async def test_each_donor_gets_their_own_card_message(session, bot):
    """Cards are edited in place, so one donor's message id must never reach another."""
    public_id = await _open_request(session, bot, units=5, donors=3)

    async with session_scope() as s:
        request = await get_request_by_public_id(s, public_id)
        links = list(
            await s.scalars(select(DonorRequest).where(DonorRequest.request_id == request.id))
        )

    chat_ids = [link.card_chat_id for link in links]
    message_ids = [link.card_message_id for link in links]
    assert sorted(chat_ids) == [1, 2, 3]
    assert len(set(message_ids)) == 3, "two donors share a card message id"


# --------------------------------------------------------------------------------------
# Onboarding state is per user
# --------------------------------------------------------------------------------------


async def test_concurrent_onboarding_keeps_each_user_state_separate():
    """FSM keys include user_id, so half-finished registrations cannot bleed together."""
    storage = MemoryStorage()

    def ctx(user_id: int) -> FSMContext:
        return FSMContext(
            storage=storage,
            key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id),
        )

    async def register(user_id: int, name: str, group: str) -> None:
        c = ctx(user_id)
        await c.set_state(Onboarding.name)
        await c.update_data(full_name=name)
        await asyncio.sleep(0)  # force interleaving at the await point
        await c.set_state(Onboarding.blood_group)
        await c.update_data(blood_group=group, district="Ernakulam")

    await asyncio.gather(
        register(101, "Anitha", "O+"),
        register(102, "Bijoy", "AB-"),
        register(103, "Carol", "B+"),
    )

    assert (await ctx(101).get_data())["full_name"] == "Anitha"
    assert (await ctx(102).get_data())["blood_group"] == "AB-"
    assert (await ctx(103).get_data())["full_name"] == "Carol"
    assert await ctx(101).get_state() == Onboarding.blood_group


async def test_one_user_abandoning_onboarding_leaves_others_untouched():
    storage = MemoryStorage()

    def ctx(user_id: int) -> FSMContext:
        return FSMContext(
            storage=storage, key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)
        )

    await ctx(201).update_data(full_name="Keeps going")
    await ctx(202).update_data(full_name="Walks away")
    await ctx(202).clear()

    assert (await ctx(201).get_data())["full_name"] == "Keeps going"
    assert await ctx(202).get_data() == {}


# --------------------------------------------------------------------------------------
# Independent requests do not interfere
# --------------------------------------------------------------------------------------


async def test_a_donor_can_hold_two_requests_at_once(session, bot):
    """Two open requests, one donor. Progress on one must not touch the other."""
    first = make_request(public_id="REQONE01", external_id="one", units=5)
    second = make_request(public_id="REQTWO02", external_id="two", units=5)
    session.add_all([first, second])
    session.add(make_donor(1))
    await session.flush()
    await run_wave(bot, session, first)
    await run_wave(bot, session, second)
    await session.commit()

    await _tap_accept(bot, "REQONE01", 1)
    await _tap_answer(bot, "REQONE01", 1, 0, True)

    async with session_scope() as s:
        one = await get_request_by_public_id(s, "REQONE01")
        two = await get_request_by_public_id(s, "REQTWO02")
        link_one = await get_donor_request(s, one.id, 1)
        link_two = await get_donor_request(s, two.id, 1)

    assert link_one.status == DonorRequestStatus.SCREENING
    assert len(link_one.answers) == 1
    assert link_two.status == DonorRequestStatus.NOTIFIED
    assert not link_two.answers


async def test_two_requests_fan_out_concurrently_without_crossing(session, bot):
    """Different districts, different pools -- run the waves at the same time."""
    ekm = make_request(public_id="EKMREQ01", external_id="ekm", units=5, district="Ernakulam")
    klm = make_request(
        public_id="KLMREQ01", external_id="klm", units=5, district="Kollam", city="Kollam"
    )
    session.add_all([ekm, klm])
    for i in range(1, 4):
        session.add(make_donor(i, district="Ernakulam", city="Kochi"))
    for i in range(4, 7):
        session.add(make_donor(i, district="Kollam", city="Kollam"))
    await session.flush()
    await session.commit()

    async def fan_out(public_id: str) -> None:
        async with session_scope() as s:
            request = await get_request_by_public_id(s, public_id)
            await run_wave(bot, s, request)

    await asyncio.gather(fan_out("EKMREQ01"), fan_out("KLMREQ01"))

    async with session_scope() as s:
        ekm = await get_request_by_public_id(s, "EKMREQ01")
        klm = await get_request_by_public_id(s, "KLMREQ01")
        ekm_donors = {
            link.donor_id
            for link in await s.scalars(
                select(DonorRequest).where(DonorRequest.request_id == ekm.id)
            )
        }
        klm_donors = {
            link.donor_id
            for link in await s.scalars(
                select(DonorRequest).where(DonorRequest.request_id == klm.id)
            )
        }

    assert ekm_donors == {1, 2, 3}
    assert klm_donors == {4, 5, 6}


async def test_a_shared_donor_pool_is_not_double_notified_across_waves(session, bot):
    """Same district, two simultaneous requests: a donor may hold both, but once each."""
    first = make_request(public_id="SHAREQ01", external_id="s1", units=5)
    second = make_request(public_id="SHAREQ02", external_id="s2", units=5)
    session.add_all([first, second])
    for i in range(1, 4):
        session.add(make_donor(i))
    await session.flush()
    await session.commit()

    async def fan_out(public_id: str) -> None:
        async with session_scope() as s:
            request = await get_request_by_public_id(s, public_id)
            await run_wave(bot, s, request)

    await asyncio.gather(fan_out("SHAREQ01"), fan_out("SHAREQ02"))

    async with session_scope() as s:
        links = list(await s.scalars(select(DonorRequest)))

    pairs = [(link.request_id, link.donor_id) for link in links]
    assert len(pairs) == len(set(pairs)), "a donor was linked to the same request twice"
    assert len(pairs) == 6  # 3 donors x 2 requests, one link each


# --------------------------------------------------------------------------------------
# Eligibility is evaluated per donor, not for the pool
# --------------------------------------------------------------------------------------


async def test_a_mixed_pool_is_filtered_per_donor(session, bot):
    request = make_request(blood_group="A+", units=10, district="Ernakulam", city="Kochi")
    session.add(request)
    session.add(make_donor(1, blood_group="A+"))  # eligible
    session.add(make_donor(2, blood_group="O-"))  # eligible, universal donor
    session.add(make_donor(3, blood_group="B+"))  # wrong group
    session.add(make_donor(4, blood_group="A+", district="Kollam", city="Kollam"))  # wrong district
    session.add(make_donor(5, blood_group="A+", last_donation=date.today()))  # cooldown
    session.add(make_donor(6, blood_group="A+", opted_out=True))  # opted out
    session.add(
        make_donor(7, blood_group="A+", snoozed_until=date.today() + timedelta(days=10))
    )  # snoozed
    session.add(make_donor(8, blood_group="A+", age=70))  # too old
    await session.flush()

    await run_wave(bot, session, request)

    notified = {link.donor_id for link in await session.scalars(select(DonorRequest))}
    assert notified == {1, 2}
