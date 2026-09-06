"""The donor's journey through one request, driven through the real handlers.

The callback objects are stubs rather than aiogram models: what is under test is the
flow -- which transitions fire, what the donor is told, what a replayed tap does -- not
Telegram's serialisation.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.bot.handlers.requests import accept, answer_question, decline
from app.bot.states import QuizCB, ReqCB
from app.core import questionnaire as quiz
from app.core.service import get_donor_request
from app.distribution import run_wave
from app.enums import DonorRequestStatus, RequestStatus, Sex
from app.models import Donor
from tests.conftest import StubQuery, make_donor, make_request


@pytest_asyncio.fixture
async def scenario(session, bot):
    """One open request with the cards already delivered to two donors."""

    async def build(*, units=1, donors=2, sex=Sex.MALE):
        request = make_request(units=units)
        session.add(request)
        for i in range(1, donors + 1):
            session.add(make_donor(i, sex=sex))
        await session.flush()
        await run_wave(bot, session, request)
        return request

    return build


async def _answer_all(query, session, donor, request, *, stop_at=None, wrong=False):
    """Walk the questionnaire, answering safely unless asked to fail one question."""
    index = 0
    while (question := quiz.question_at(donor.sex, index)) is not None:
        fail_here = wrong and question.id == stop_at
        answer = question.disqualifying_answer if fail_here else not question.disqualifying_answer
        await answer_question(
            query, QuizCB(pid=request.public_id, idx=index, ans=int(answer)), session, donor
        )
        if fail_here:
            return index
        index += 1
    return index


# --------------------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------------------


async def test_accept_screen_confirm(session, bot, scenario):
    request = await scenario(units=1)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)

    await accept(query, ReqCB(action="acc", pid=request.public_id), session, donor)
    link = await get_donor_request(session, request.id, 1)
    assert link.status == DonorRequestStatus.ACCEPTED
    assert len(query.message.answers) == 1  # first question asked

    await _answer_all(query, session, donor, request)

    await session.refresh(link)
    await session.refresh(request)
    assert link.status == DonorRequestStatus.CONFIRMED
    assert request.confirmed_count == 1
    assert request.status == RequestStatus.FILLED

    confirmation = query.message.answers[-1]
    assert "General Hospital" in confirmation
    assert "MG Road" in confirmation


async def test_confirmation_tells_the_donor_when_to_arrive(session, bot, scenario):
    request = await scenario(units=1)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)

    await accept(query, ReqCB(action="acc", pid=request.public_id), session, donor)
    await _answer_all(query, session, donor, request)

    assert "before" in query.message.answers[-1].lower()


async def test_female_donor_answers_the_extra_question(session, bot, scenario):
    request = await scenario(units=1, sex=Sex.FEMALE)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)

    await accept(query, ReqCB(action="acc", pid=request.public_id), session, donor)
    asked = await _answer_all(query, session, donor, request)

    assert asked == quiz.total_questions(Sex.FEMALE)
    link = await get_donor_request(session, request.id, 1)
    assert link.status == DonorRequestStatus.CONFIRMED
    assert set(link.answers) == {q.id for q in quiz.questions_for(Sex.FEMALE)}


# --------------------------------------------------------------------------------------
# The gate (P0-8)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("question_id", ["recent_illness", "medication", "tattoo", "alcohol"])
async def test_a_temporary_condition_ends_this_request_only(session, bot, scenario, question_id):
    request = await scenario(units=1)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)

    await accept(query, ReqCB(action="acc", pid=request.public_id), session, donor)
    await _answer_all(query, session, donor, request, stop_at=question_id, wrong=True)

    link = await get_donor_request(session, request.id, 1)
    await session.refresh(link)
    await session.refresh(request)
    await session.refresh(donor)

    assert link.status == DonorRequestStatus.ELIMINATED
    assert link.eliminated_reason == question_id
    # The donor's standing is untouched: still registered, no review flag, no unit taken.
    assert donor.is_registered is True
    assert donor.opted_out is False
    assert donor.review_flag is False
    assert request.confirmed_count == 0
    assert request.status == RequestStatus.OPEN


async def test_elimination_is_never_phrased_as_a_verdict(session, bot, scenario):
    request = await scenario(units=1)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)

    await accept(query, ReqCB(action="acc", pid=request.public_id), session, donor)
    await _answer_all(query, session, donor, request, stop_at="recent_illness", wrong=True)

    message = query.message.edits[-1].lower()
    assert "registration" in message
    assert "unfit" not in message and "rejected" not in message


async def test_being_underweight_is_flagged_for_review(session, bot, scenario):
    request = await scenario(units=1)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)

    await accept(query, ReqCB(action="acc", pid=request.public_id), session, donor)
    await _answer_all(query, session, donor, request, stop_at="weight", wrong=True)

    await session.refresh(donor)
    assert donor.review_flag is True
    assert donor.review_reason == "weight"


# --------------------------------------------------------------------------------------
# Contention and replays (P0-7, PRD 12)
# --------------------------------------------------------------------------------------


async def test_the_second_donor_through_screening_is_waitlisted(session, bot, scenario):
    """Both accept while the request is open, then both finish screening."""
    request = await scenario(units=1, donors=2)
    first, second = await session.get(Donor, 1), await session.get(Donor, 2)
    q1, q2 = StubQuery(bot, 1), StubQuery(bot, 2)

    await accept(q1, ReqCB(action="acc", pid=request.public_id), session, first)
    await accept(q2, ReqCB(action="acc", pid=request.public_id), session, second)

    await _answer_all(q1, session, first, request)
    await _answer_all(q2, session, second, request)

    link1 = await get_donor_request(session, request.id, 1)
    link2 = await get_donor_request(session, request.id, 2)
    await session.refresh(request)

    assert link1.status == DonorRequestStatus.CONFIRMED
    assert link2.status == DonorRequestStatus.REQUEST_FILLED
    assert request.confirmed_count == 1
    assert "first in line" in q2.message.answers[-1].lower()


async def test_accepting_after_the_units_are_met_joins_the_waitlist(session, bot, scenario):
    """No point asking six questions for a place that no longer exists (PRD 7.2)."""
    request = await scenario(units=1, donors=2)
    first, second = await session.get(Donor, 1), await session.get(Donor, 2)

    q1 = StubQuery(bot, 1)
    await accept(q1, ReqCB(action="acc", pid=request.public_id), session, first)
    await _answer_all(q1, session, first, request)
    await session.refresh(request)
    assert request.status == RequestStatus.FILLED

    q2 = StubQuery(bot, 2)
    await accept(q2, ReqCB(action="acc", pid=request.public_id), session, second)

    link2 = await get_donor_request(session, request.id, 2)
    assert link2.status == DonorRequestStatus.REQUEST_FILLED
    assert link2.waitlisted_at is not None
    assert "do not travel" in q2.message.answers[-1].lower()
    assert len(q2.message.answers) == 1  # no questionnaire


async def test_a_replayed_accept_does_not_re_ask_the_questionnaire(session, bot, scenario):
    request = await scenario(units=1)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)
    payload = ReqCB(action="acc", pid=request.public_id)

    await accept(query, payload, session, donor)
    await accept(query, payload, session, donor)

    assert len(query.message.answers) == 1


async def test_a_replayed_answer_is_ignored(session, bot, scenario):
    request = await scenario(units=1)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)

    await accept(query, ReqCB(action="acc", pid=request.public_id), session, donor)
    payload = QuizCB(pid=request.public_id, idx=0, ans=1)
    await answer_question(query, payload, session, donor)
    edits_after_first = len(query.message.edits)
    await answer_question(query, payload, session, donor)

    link = await get_donor_request(session, request.id, 1)
    assert len(link.answers) == 1
    assert len(query.message.edits) == edits_after_first


async def test_answering_out_of_order_is_ignored(session, bot, scenario):
    request = await scenario(units=1)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)

    await accept(query, ReqCB(action="acc", pid=request.public_id), session, donor)
    # A tap from a card further down the flow than the donor actually is.
    await answer_question(query, QuizCB(pid=request.public_id, idx=3, ans=1), session, donor)

    link = await get_donor_request(session, request.id, 1)
    assert link.answers in (None, {})


async def test_accepting_a_cancelled_request_tells_the_donor_it_is_closed(session, bot, scenario):
    request = await scenario(units=2, donors=1)
    donor = await session.get(Donor, 1)

    request.status = RequestStatus.CANCELLED
    await session.flush()

    query = StubQuery(bot, 1)
    await accept(query, ReqCB(action="acc", pid=request.public_id), session, donor)

    link = await get_donor_request(session, request.id, 1)
    assert link.status == DonorRequestStatus.NOTIFIED  # never entered screening
    assert "withdrawn" in query.message.answers[-1].lower()


# --------------------------------------------------------------------------------------
# Declining (P0-6)
# --------------------------------------------------------------------------------------


async def test_declining_records_the_response_and_never_pings_again(session, bot, scenario):
    request = await scenario(units=5, donors=2)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)

    await decline(query, ReqCB(action="dec", pid=request.public_id), session, donor)
    link = await get_donor_request(session, request.id, 1)
    assert link.status == DonorRequestStatus.DECLINED

    sent_before = len(bot.sent)
    await run_wave(bot, session, request)
    assert len(bot.sent) == sent_before  # not re-notified by the next wave


async def test_a_replayed_decline_does_not_message_twice(session, bot, scenario):
    request = await scenario(units=5)
    donor = await session.get(Donor, 1)
    query = StubQuery(bot, 1)
    payload = ReqCB(action="dec", pid=request.public_id)

    await decline(query, payload, session, donor)
    await decline(query, payload, session, donor)

    assert len(query.message.answers) == 1
