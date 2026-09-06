"""Request response: accept, decline, screen, confirm (PRD P0-3, P0-6, P0-7, P0-8).

Progress through the questionnaire is stored on the ``DonorRequest`` row, not in FSM
memory, so the flow survives a restart and a replayed tap is detected by comparing the
tapped question index against the number of answers already recorded.
"""

from __future__ import annotations

import logging
from datetime import date

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.admin import refresh_admin_cards
from app.bot.render import card_text, deliver_card, fmt_dt, update_card
from app.bot.states import QuizCB, ReqCB
from app.config import settings
from app.core import questionnaire as quiz
from app.core.eligibility import explain_ineligibility, next_eligible_date
from app.core.service import (
    ConfirmOutcome,
    confirm_or_waitlist,
    ensure_donor_request,
    get_donor_request,
    get_request_by_public_id,
    log_event,
    set_answers,
    transition,
)
from app.enums import DonorRequestStatus, RequestStatus
from app.i18n import t
from app.integration.demand import record_confirmation
from app.models import Admin, BloodRequest, Donor, DonorRequest, utcnow

log = logging.getLogger(__name__)
router = Router(name="requests")

#: Statuses whose card still carries live Accept / Not-this-time buttons.
OPEN_TO_RESPONSE = (DonorRequestStatus.NOTIFIED,)


# --------------------------------------------------------------------------------------
# Deep-link landing (P0-3)
# --------------------------------------------------------------------------------------


async def show_request_by_public_id(
    message: Message,
    session: AsyncSession,
    donor: Donor,
    public_id: str,
    *,
    attribute: bool = False,
) -> None:
    """Land a donor on the request their link pointed at."""
    request = await get_request_by_public_id(session, public_id)
    if request is None:
        await message.answer(t("request.not_found", donor.language))
        return

    if attribute and donor.source_request_id is None:
        # Which forwarded link brought this donor in (P1 attribution analytics).
        donor.source_request_id = request.id

    if request.status != RequestStatus.OPEN:
        await message.answer(_closed_text(request, donor.language))
        return

    existing = await get_donor_request(session, request.id, donor.telegram_user_id)
    if existing is not None and existing.status not in OPEN_TO_RESPONSE:
        await message.answer(t("request.ineligible.ALREADY_ENGAGED", donor.language))
        return

    reason = explain_ineligibility(donor, request, date.today())
    if reason is not None:
        await message.answer(_ineligible_text(reason, donor, request))
        return

    if existing is not None:
        # Already notified: re-post the card so the link lands on something tappable.
        await message.answer(
            card_text(request, donor.language),
            reply_markup=kb.request_card(donor.language, request.public_id),
        )
        return

    link, _ = await ensure_donor_request(
        session, request.id, donor.telegram_user_id, wave=request.wave_index
    )
    await deliver_card(message.bot, session, donor, request, link)
    await log_event(
        session,
        "request.opened_via_link",
        donor_id=donor.telegram_user_id,
        request_id=request.id,
    )


def _closed_text(request: BloodRequest, lang: str) -> str:
    if request.status == RequestStatus.EXPIRED:
        return t("request.expired", lang, needed_by=fmt_dt(request.needed_by))
    if request.status == RequestStatus.CANCELLED:
        return t("request.cancelled", lang)
    return t("request.closed_thanks", lang)


def _ineligible_text(reason, donor: Donor, request: BloodRequest) -> str:
    lang = donor.language
    next_date = (
        next_eligible_date(donor.last_donation_date, donor.sex).strftime("%d %b %Y")
        if donor.last_donation_date
        else ""
    )
    return t(
        f"request.ineligible.{reason.value}",
        lang,
        blood_group=request.blood_group,
        district=request.district,
        donor_district=donor.district or "",
        min_age=settings.min_age,
        max_age=settings.max_age,
        next_date=next_date,
        until=donor.snoozed_until.strftime("%d %b %Y") if donor.snoozed_until else "",
    )


# --------------------------------------------------------------------------------------
# Accept / decline (P0-6)
# --------------------------------------------------------------------------------------


@router.callback_query(ReqCB.filter(F.action == "dec"))
async def decline(
    query: CallbackQuery, callback_data: ReqCB, session: AsyncSession, donor: Donor | None
) -> None:
    context = await _load(query, callback_data, session, donor)
    if context is None:
        return
    request, link = context

    moved = await transition(
        session,
        link,
        DonorRequestStatus.DECLINED,
        expected=OPEN_TO_RESPONSE,
        responded_at=utcnow(),
    )
    if moved:
        await update_card(
            query.bot,
            link,
            f"{card_text(request, donor.language)}\n\n"
            f"<i>{t('confirmation.card_declined', donor.language)}</i>",
        )
        await query.message.answer(t("request.declined_ack", donor.language))


@router.callback_query(ReqCB.filter(F.action == "acc"))
async def accept(
    query: CallbackQuery, callback_data: ReqCB, session: AsyncSession, donor: Donor | None
) -> None:
    context = await _load(query, callback_data, session, donor)
    if context is None:
        return
    request, link = context

    if request.status == RequestStatus.FILLED:
        # PRD 7.2: a donor who says yes after the units are met joins the waitlist
        # rather than being turned away, so a cancellation has somewhere to go.
        await _waitlist(query, session, donor, request, link)
        return
    if request.status != RequestStatus.OPEN:
        await _close_own_card(query, request, link, donor.language)
        return

    moved = await transition(
        session,
        link,
        DonorRequestStatus.ACCEPTED,
        expected=OPEN_TO_RESPONSE,
        responded_at=utcnow(),
        answers={},
    )
    if not moved:
        # A duplicate tap, or the donor already answered. Nothing to redo.
        return

    await update_card(
        query.bot,
        link,
        f"{card_text(request, donor.language)}\n\n"
        f"<i>{t('request.accepted_ack', donor.language)}</i>",
    )
    await _ask_question(query.message, donor, request, link, index=0)


# --------------------------------------------------------------------------------------
# Questionnaire (P0-8)
# --------------------------------------------------------------------------------------


async def _ask_question(
    message: Message, donor: Donor, request: BloodRequest, link: DonorRequest, index: int
) -> None:
    question = quiz.question_at(donor.sex, index)
    if question is None:
        return
    total = quiz.total_questions(donor.sex)
    body = (
        f"<b>{t('questionnaire.intro', donor.language, index=index + 1, total=total)}</b>\n\n"
        f"{t(question.key, donor.language)}"
    )
    await message.answer(body, reply_markup=kb.quiz(donor.language, request.public_id, index))


@router.callback_query(QuizCB.filter())
async def answer_question(
    query: CallbackQuery, callback_data: QuizCB, session: AsyncSession, donor: Donor | None
) -> None:
    context = await _load(query, callback_data, session, donor)
    if context is None:
        return
    request, link = context

    if link.status not in (DonorRequestStatus.ACCEPTED, DonorRequestStatus.SCREENING):
        return

    answers = dict(link.answers or {})
    expected_index = len(answers)
    if callback_data.idx != expected_index:
        # A stale card from a redelivered update; the donor has already moved past it.
        return

    question = quiz.question_at(donor.sex, callback_data.idx)
    if question is None:
        return

    answer = bool(callback_data.ans)
    answers[question.id] = answer

    if quiz.is_disqualifying(question, answer):
        await _eliminate(query, session, donor, request, link, question, answers)
        return

    if link.status == DonorRequestStatus.ACCEPTED:
        await transition(
            session,
            link,
            DonorRequestStatus.SCREENING,
            expected=(DonorRequestStatus.ACCEPTED,),
            answers=answers,
        )
    else:
        await set_answers(session, link, answers)

    next_index = callback_data.idx + 1
    if quiz.question_at(donor.sex, next_index) is not None:
        total = quiz.total_questions(donor.sex)
        next_question = quiz.question_at(donor.sex, next_index)
        await query.message.edit_text(
            f"<b>{t('questionnaire.intro', donor.language, index=next_index + 1, total=total)}</b>"
            f"\n\n{t(next_question.key, donor.language)}",
            reply_markup=kb.quiz(donor.language, request.public_id, next_index),
        )
        return

    await query.message.edit_reply_markup(reply_markup=None)
    await _resolve(query, session, donor, request, link)


async def _eliminate(
    query: CallbackQuery,
    session: AsyncSession,
    donor: Donor,
    request: BloodRequest,
    link: DonorRequest,
    question: quiz.Question,
    answers: dict[str, bool],
) -> None:
    """A disqualifying answer ends this request only -- the profile is untouched."""
    await transition(
        session,
        link,
        DonorRequestStatus.ELIMINATED,
        expected=(DonorRequestStatus.ACCEPTED, DonorRequestStatus.SCREENING),
        eliminated_reason=question.id,
        answers=answers,
    )

    if question.fail_kind == quiz.FailKind.REVIEW:
        donor.review_flag = True
        donor.review_reason = question.id
        await session.flush()

    await query.message.edit_text(
        t(
            "questionnaire.eliminated",
            donor.language,
            reason=t(question.fail_key, donor.language).strip(),
        ),
        reply_markup=None,
    )
    await update_card(
        query.bot,
        link,
        f"{card_text(request, donor.language)}\n\n"
        f"<i>{t('confirmation.card_eliminated', donor.language)}</i>",
    )
    await log_event(
        session,
        "donor_request.eliminated",
        donor_id=donor.telegram_user_id,
        request_id=request.id,
        question=question.id,
    )


# --------------------------------------------------------------------------------------
# Confirmation / waitlist (P0-7)
# --------------------------------------------------------------------------------------


async def _resolve(
    query: CallbackQuery,
    session: AsyncSession,
    donor: Donor,
    request: BloodRequest,
    link: DonorRequest,
) -> None:
    from app.distribution import publish_state

    result = await confirm_or_waitlist(session, link, request)

    if result.outcome == ConfirmOutcome.CONFIRMED:
        await query.message.answer(_confirmation_text(request, donor.language))
        await update_card(
            query.bot,
            link,
            f"{card_text(request, donor.language)}\n\n"
            f"<i>{t('confirmation.card_confirmed', donor.language)}</i>",
        )
        await record_confirmation(session, request, donor)
        if result.just_filled:
            from app.distribution import close_pending_cards

            await close_pending_cards(query.bot, session, request, "confirmation.card_filled")
        await publish_state(query.bot, session, request)
        return

    if result.outcome == ConfirmOutcome.WAITLISTED:
        await publish_state(query.bot, session, request)
        await query.message.answer(t("waitlist.placed", donor.language))
        await update_card(
            query.bot,
            link,
            f"{card_text(request, donor.language)}\n\n"
            f"<i>{t('confirmation.card_filled', donor.language)}</i>",
        )
        return

    if result.outcome == ConfirmOutcome.REQUEST_CLOSED:
        await query.message.answer(_closed_text(request, donor.language))


async def _waitlist(
    query: CallbackQuery,
    session: AsyncSession,
    donor: Donor,
    request: BloodRequest,
    link: DonorRequest,
) -> None:
    """Record a late acceptance as a waitlist place and say so plainly."""
    moved = await transition(
        session,
        link,
        DonorRequestStatus.REQUEST_FILLED,
        expected=OPEN_TO_RESPONSE,
        responded_at=utcnow(),
        waitlisted_at=utcnow(),
    )
    if not moved:
        return
    await update_card(
        query.bot,
        link,
        f"{card_text(request, donor.language)}\n\n"
        f"<i>{t('confirmation.card_filled', donor.language)}</i>",
    )
    await query.message.answer(t("request.filled_meanwhile", donor.language))


def _confirmation_text(request: BloodRequest, lang: str) -> str:
    when = (
        t("confirmation.when_slot", lang, time=fmt_dt(request.slot_time))
        if request.slot_time
        else t("confirmation.when_before", lang, time=fmt_dt(request.needed_by))
    )
    return t(
        "confirmation.confirmed",
        lang,
        hospital=request.hospital_name,
        address=request.hospital_address,
        when=when,
    )


# --------------------------------------------------------------------------------------
# Admin: refresh the live counter (P0-12)
# --------------------------------------------------------------------------------------


@router.callback_query(F.data.startswith("adm:ref:"))
async def admin_refresh(query: CallbackQuery, session: AsyncSession) -> None:
    admin = await session.get(Admin, query.from_user.id)
    if admin is None or not admin.active:
        await query.answer(t("admin.not_admin", settings.locale), show_alert=True)
        return
    request = await get_request_by_public_id(session, query.data.split(":")[-1])
    if request is None:
        await query.answer(t("request.not_found", settings.locale), show_alert=True)
        return
    await refresh_admin_cards(query.bot, session, request)
    await query.answer(t("admin.refreshed", settings.locale))


# --------------------------------------------------------------------------------------
# Shared loading
# --------------------------------------------------------------------------------------


async def _load(
    query: CallbackQuery,
    callback_data: ReqCB | QuizCB,
    session: AsyncSession,
    donor: Donor | None,
) -> tuple[BloodRequest, DonorRequest] | None:
    """Resolve the request and this donor's link, answering the query when it cannot."""
    if donor is None or not donor.is_registered:
        await query.answer(t("request.ineligible.NOT_REGISTERED", settings.locale), show_alert=True)
        return None

    request = await get_request_by_public_id(session, callback_data.pid)
    if request is None:
        await query.answer(t("request.not_found", donor.language), show_alert=True)
        return None

    link = await get_donor_request(session, request.id, donor.telegram_user_id)
    if link is None:
        await query.answer(t("request.not_found", donor.language), show_alert=True)
        return None

    return request, link


async def _close_own_card(
    query: CallbackQuery, request: BloodRequest, link: DonorRequest, lang: str
) -> None:
    note = (
        "confirmation.card_expired"
        if request.status == RequestStatus.EXPIRED
        else "confirmation.card_filled"
    )
    await update_card(
        query.bot,
        link,
        f"{card_text(request, lang)}\n\n<i>{t(note, lang)}</i>",
    )
    await query.message.answer(_closed_text(request, lang))
