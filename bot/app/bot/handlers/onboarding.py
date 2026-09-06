"""Onboarding and deep-link entry (PRD 7.3, P0-2 and P0-3).

The donor types exactly one thing -- their name. Everything else, dates included, is a
button. The flow keeps partial answers in FSM state and only writes a registered donor
row at the consent step, so an abandoned registration leaves nothing behind.

A donor who arrived on ``?start=req_<id>`` has that request parked in state and is taken
straight back to it the moment registration finishes.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.states import OnbCB, Onboarding
from app.config import settings
from app.core.eligibility import age_on, next_eligible_date
from app.core.service import log_event
from app.enums import BloodGroup
from app.i18n import t, tl
from app.ids import parse_start_payload
from app.models import Donor, utcnow

log = logging.getLogger(__name__)
router = Router(name="onboarding")

LANG = settings.locale


# --------------------------------------------------------------------------------------
# Entry
# --------------------------------------------------------------------------------------


@router.message(CommandStart(deep_link=True))
@router.message(CommandStart())
async def start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    donor: Donor | None,
) -> None:
    public_id = parse_start_payload(command.args)

    if donor is not None and donor.is_registered:
        # Import here: the request handlers import this module's router indirectly.
        from app.bot.handlers.requests import show_request_by_public_id

        if public_id:
            await show_request_by_public_id(message, session, donor, public_id)
        else:
            await message.answer(
                t(
                    "onboarding.already_registered",
                    donor.language,
                    name=donor.full_name or "",
                    blood_group=donor.blood_group,
                )
            )
        return

    await state.clear()
    if public_id:
        await state.update_data(pending_request=public_id)
    await log_event(
        session,
        "onboarding.started",
        donor_id=message.from_user.id if message.from_user else None,
        via_deep_link=bool(public_id),
    )

    await message.answer(
        t("onboarding.welcome_from_request" if public_id else "onboarding.welcome", LANG)
    )
    await message.answer(t("onboarding.ask_contact", LANG), reply_markup=kb.contact_request(LANG))
    await state.set_state(Onboarding.contact)


# --------------------------------------------------------------------------------------
# Contact -> name
# --------------------------------------------------------------------------------------


@router.message(F.contact)
async def got_contact(message: Message, state: FSMContext, donor: Donor | None) -> None:
    """Accept a shared contact in any state, not only mid-onboarding.

    The reply keyboard stays visible in the chat long after the bot restarts, so a donor
    can tap "Share my number" when the server has no state for them. Filtering this on
    ``Onboarding.contact`` meant that tap matched nothing and the bot said nothing at
    all, which is indistinguishable from being broken.
    """
    if donor is not None and donor.is_registered:
        await message.answer(
            t(
                "onboarding.already_registered",
                donor.language,
                name=donor.full_name or "",
                blood_group=donor.blood_group,
            ),
            reply_markup=kb.remove_keyboard(),
        )
        return

    contact = message.contact
    if contact.user_id is None or contact.user_id != message.from_user.id:
        await message.answer(
            t("onboarding.contact_not_own", LANG), reply_markup=kb.contact_request(LANG)
        )
        return

    await state.update_data(phone=_normalise_phone(contact.phone_number))
    await message.answer(t("onboarding.ask_name", LANG), reply_markup=kb.remove_keyboard())
    await state.set_state(Onboarding.name)


@router.message(Onboarding.contact)
async def contact_nudge(message: Message) -> None:
    """Anything that is not a contact while we are waiting for one.

    Usually the donor typed their number instead of tapping. Repeating the same prompt
    reads as a loop, so say why the button is necessary.
    """
    await message.answer(t("onboarding.contact_typed", LANG), reply_markup=kb.contact_request(LANG))


def _normalise_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    return f"+{digits}"


@router.message(Onboarding.name, F.text)
async def got_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(t("onboarding.name_too_short", LANG))
        return
    await state.update_data(full_name=name[:120])
    await message.answer(t("onboarding.ask_dob_year", LANG), reply_markup=kb.dob_years(LANG))
    await state.set_state(Onboarding.dob_year)


# --------------------------------------------------------------------------------------
# Date of birth
# --------------------------------------------------------------------------------------


@router.callback_query(Onboarding.dob_year, OnbCB.filter(F.field == "dob_page"))
async def page_years(query: CallbackQuery, callback_data: OnbCB) -> None:
    await query.message.edit_reply_markup(reply_markup=kb.dob_years(LANG, callback_data.page))


@router.callback_query(Onboarding.dob_year, OnbCB.filter(F.field == "dob_year"))
async def got_dob_year(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    await state.update_data(dob_year=int(callback_data.value))
    await query.message.edit_text(
        t("onboarding.ask_dob_month", LANG), reply_markup=kb.months(LANG, "dob_month")
    )
    await state.set_state(Onboarding.dob_month)


@router.callback_query(Onboarding.dob_month, OnbCB.filter(F.field == "dob_month"))
async def got_dob_month(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    data = await state.update_data(dob_month=int(callback_data.value))
    await query.message.edit_text(
        t("onboarding.ask_dob_day", LANG),
        reply_markup=kb.days(LANG, "dob_day", data["dob_year"], data["dob_month"]),
    )
    await state.set_state(Onboarding.dob_day)


@router.callback_query(Onboarding.dob_day, OnbCB.filter(F.field == "dob_day"))
async def got_dob_day(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    data = await state.get_data()
    dob = date(data["dob_year"], data["dob_month"], int(callback_data.value))

    # The year grid already bounds the range; this catches an edge birthday this year.
    age = age_on(dob, date.today())
    if age < settings.min_age:
        await query.message.edit_text(t("onboarding.age_too_young", LANG, min_age=settings.min_age))
        await state.clear()
        return
    if age > settings.max_age:
        await query.message.edit_text(t("onboarding.age_too_old", LANG, max_age=settings.max_age))
        await state.clear()
        return

    await state.update_data(dob=dob.isoformat())
    await query.message.edit_text(t("onboarding.ask_sex", LANG), reply_markup=kb.sexes(LANG))
    await state.set_state(Onboarding.sex)


# --------------------------------------------------------------------------------------
# Sex -> blood group -> district -> city
# --------------------------------------------------------------------------------------


@router.callback_query(Onboarding.sex, OnbCB.filter(F.field == "sex"))
async def got_sex(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    await state.update_data(sex=callback_data.value)
    await query.message.edit_text(
        t("onboarding.ask_blood_group", LANG), reply_markup=kb.blood_groups(LANG)
    )
    await state.set_state(Onboarding.blood_group)


@router.callback_query(Onboarding.blood_group, OnbCB.filter(F.field == "blood_group"))
async def got_blood_group(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    await state.update_data(blood_group=callback_data.value)
    if callback_data.value == BloodGroup.UNKNOWN:
        await query.message.answer(t("onboarding.blood_group_unknown_note", LANG))
    await query.message.edit_text(
        t("onboarding.ask_district", LANG), reply_markup=kb.districts(LANG)
    )
    await state.set_state(Onboarding.district)


@router.callback_query(Onboarding.district, OnbCB.filter(F.field == "district"))
async def got_district(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    names = tl("regions.districts", LANG)
    index = int(callback_data.value)
    if not 0 <= index < len(names):
        await query.message.edit_text(
            t("onboarding.ask_district", LANG), reply_markup=kb.districts(LANG)
        )
        return
    district = names[index]
    await state.update_data(district=district)
    await query.message.edit_text(
        t("onboarding.ask_city", LANG), reply_markup=kb.cities(LANG, district)
    )
    await state.set_state(Onboarding.city)


@router.callback_query(Onboarding.city, OnbCB.filter(F.field == "city"))
async def got_city(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    data = await state.get_data()
    district = data["district"]
    index = int(callback_data.value)
    towns = tl(f"regions.cities.{district}", LANG)
    # -1 is "somewhere else in this district": district is what gates eligibility, so an
    # unlisted town only costs the donor their place in the same-city ordering.
    city = towns[index] if 0 <= index < len(towns) else district

    await state.update_data(city=city)
    await query.message.edit_text(
        t("onboarding.ask_donated_before", LANG), reply_markup=kb.yes_no(LANG, "donated_before")
    )
    await state.set_state(Onboarding.donated_before)


# --------------------------------------------------------------------------------------
# Donation history
# --------------------------------------------------------------------------------------


@router.callback_query(Onboarding.donated_before, OnbCB.filter(F.field == "donated_before"))
async def got_donated_before(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    if callback_data.value == "0":
        await _ask_consent(query, state)
        return
    await query.message.edit_text(
        t("onboarding.ask_last_donation_year", LANG), reply_markup=kb.last_donation_years(LANG)
    )
    await state.set_state(Onboarding.last_year)


@router.callback_query(Onboarding.last_year, OnbCB.filter(F.field == "last_year"))
async def got_last_year(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    if callback_data.value == "0":
        # Cannot remember: leave the date empty rather than guess a cooldown.
        await _ask_consent(query, state)
        return
    await state.update_data(last_year=int(callback_data.value))
    await query.message.edit_text(
        t("onboarding.ask_last_donation_month", LANG), reply_markup=kb.months(LANG, "last_month")
    )
    await state.set_state(Onboarding.last_month)


@router.callback_query(Onboarding.last_month, OnbCB.filter(F.field == "last_month"))
async def got_last_month(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    data = await state.update_data(last_month=int(callback_data.value))
    await query.message.edit_text(
        t("onboarding.ask_last_donation_day", LANG),
        reply_markup=kb.days(LANG, "last_day", data["last_year"], data["last_month"]),
    )
    await state.set_state(Onboarding.last_day)


@router.callback_query(Onboarding.last_day, OnbCB.filter(F.field == "last_day"))
async def got_last_day(query: CallbackQuery, callback_data: OnbCB, state: FSMContext) -> None:
    data = await state.get_data()
    year, month = data["last_year"], data["last_month"]
    day = min(int(callback_data.value), calendar.monthrange(year, month)[1])
    last = date(year, month, day)

    if last > date.today():
        await query.message.edit_text(
            t("onboarding.last_donation_future", LANG), reply_markup=kb.last_donation_years(LANG)
        )
        await state.set_state(Onboarding.last_year)
        return

    await state.update_data(last_donation_date=last.isoformat())
    await _ask_consent(query, state)


async def _ask_consent(query: CallbackQuery, state: FSMContext) -> None:
    await query.message.edit_text(t("onboarding.ask_consent", LANG), reply_markup=kb.consent(LANG))
    await state.set_state(Onboarding.consent)


# --------------------------------------------------------------------------------------
# Consent -> the donor row
# --------------------------------------------------------------------------------------


@router.callback_query(Onboarding.consent, OnbCB.filter(F.field == "consent"))
async def got_consent(
    query: CallbackQuery, callback_data: OnbCB, state: FSMContext, session: AsyncSession
) -> None:
    if callback_data.value == "0":
        await query.message.edit_text(t("onboarding.consent_declined", LANG))
        await state.clear()
        return

    data = await state.get_data()
    donor = await _persist_donor(session, query.from_user.id, data)
    await state.clear()

    group = donor.blood_group
    done_key = "onboarding.done_unknown_group" if group == BloodGroup.UNKNOWN else "onboarding.done"
    await query.message.edit_text(
        t(
            done_key,
            donor.language,
            name=donor.full_name or "",
            blood_group=group,
            city=donor.city or donor.district or "",
        )
    )

    if donor.last_donation_date:
        eligible_from = next_eligible_date(donor.last_donation_date, donor.sex)
        if eligible_from > date.today():
            await query.message.answer(
                t(
                    "onboarding.cooldown_note",
                    donor.language,
                    date=eligible_from.strftime("%d %b %Y"),
                )
            )

    await log_event(session, "onboarding.completed", donor_id=donor.telegram_user_id)

    pending = data.get("pending_request")
    if pending:
        from app.bot.handlers.requests import show_request_by_public_id

        await show_request_by_public_id(query.message, session, donor, pending, attribute=True)


async def _persist_donor(session: AsyncSession, user_id: int, data: dict) -> Donor:
    donor = await session.get(Donor, user_id)
    if donor is None:
        donor = Donor(telegram_user_id=user_id)
        session.add(donor)

    phone = data.get("phone")
    if phone:
        # The number moved to a new Telegram account: detach it from the old record
        # rather than violating the unique constraint mid-registration.
        previous = await session.scalar(
            select(Donor).where(Donor.phone == phone, Donor.telegram_user_id != user_id)
        )
        if previous is not None:
            previous.phone = None
            await log_event(
                session,
                "donor.phone_reassigned",
                donor_id=user_id,
                previous_donor_id=previous.telegram_user_id,
            )
            await session.flush()

    donor.phone = phone
    donor.full_name = data.get("full_name")
    donor.dob = date.fromisoformat(data["dob"]) if data.get("dob") else None
    donor.sex = data.get("sex")
    donor.blood_group = data.get("blood_group", BloodGroup.UNKNOWN)
    donor.district = data.get("district")
    donor.city = data.get("city")
    donor.last_donation_date = (
        date.fromisoformat(data["last_donation_date"]) if data.get("last_donation_date") else None
    )
    donor.is_registered = True
    donor.opted_out = False
    donor.consent_at = utcnow()
    donor.language = LANG
    await session.flush()
    return donor
