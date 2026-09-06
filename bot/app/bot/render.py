"""Rendering and delivery of request cards.

Two rules from the PRD live here:

- **Edit, never re-send.** A donor's chat holds exactly one message per request; every
  status change edits that message in place (PRD 12).
- **Nothing about the patient.** A card carries blood group, hospital, units and time.
  No names, no attender numbers (PRD 4).
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import settings
from app.core.service import as_utc, log_event
from app.i18n import t
from app.models import BloodRequest, Donor, DonorRequest, utcnow

log = logging.getLogger(__name__)


def _display_tz() -> ZoneInfo:
    """Fall back to UTC rather than refusing to start on a host with no tz database."""
    try:
        return ZoneInfo(settings.display_timezone)
    except ZoneInfoNotFoundError:
        log.warning("timezone %s unavailable; showing UTC", settings.display_timezone)
        return ZoneInfo("UTC")


DISPLAY_TZ = _display_tz()


def fmt_dt(value: datetime) -> str:
    """Render a stored UTC timestamp in the donors' local timezone."""
    return as_utc(value).astimezone(DISPLAY_TZ).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def fmt_day(value: datetime) -> str:
    """Just the day, for requests the bank raised with a date rather than a time."""
    return as_utc(value).astimezone(DISPLAY_TZ).strftime("%a %d %b").replace(" 0", " ")


def fmt_needed_by(request: BloodRequest, lang: str) -> str:
    """A bank demand carries a day; an API request carries a time. Say the right one."""
    if request.demand_id:
        return t("request.needed_by_day", lang, day=fmt_day(request.needed_by))
    return t("request.needed_by_time", lang, time=fmt_dt(request.needed_by))


def card_text(request: BloodRequest, lang: str) -> str:
    units_key = "request.units_one" if request.units_needed == 1 else "request.units_many"
    units_line = t(
        units_key,
        lang,
        units_needed=request.units_needed,
        units_remaining=request.units_remaining,
    )
    key = "request.card_with_notes" if request.notes else "request.card"
    return t(
        key,
        lang,
        blood_group=request.blood_group,
        hospital=request.hospital_name,
        city=request.city or request.district,
        district=request.district,
        needed_by=fmt_needed_by(request, lang),
        units_line=units_line,
        notes=request.notes or "",
    )


async def deliver_card(
    bot: Bot,
    session: AsyncSession,
    donor: Donor,
    request: BloodRequest,
    link: DonorRequest,
) -> bool:
    """Send the request card and remember the message so we can edit it later.

    Returns False when the donor has blocked the bot -- they are opted out rather than
    retried forever, which also keeps the block-rate metric honest (PRD 9).
    """
    try:
        message = await bot.send_message(
            chat_id=donor.telegram_user_id,
            text=card_text(request, donor.language),
            reply_markup=kb.request_card(donor.language, request.public_id),
        )
    except TelegramForbiddenError:
        donor.opted_out = True
        await log_event(
            session, "donor.blocked", donor_id=donor.telegram_user_id, request_id=request.id
        )
        return False
    except TelegramRetryAfter as exc:
        log.warning("flood limit hit, wave will retry: %s", exc)
        return False
    except TelegramBadRequest as exc:
        log.warning("could not deliver card to %s: %s", donor.telegram_user_id, exc)
        return False

    link.card_chat_id = message.chat.id
    link.card_message_id = message.message_id
    link.notified_at = utcnow()
    await log_event(
        session,
        "donor_request.notified",
        donor_id=donor.telegram_user_id,
        request_id=request.id,
        wave=link.wave,
    )
    return True


async def update_card(
    bot: Bot,
    link: DonorRequest,
    text: str,
    *,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit a donor's card in place. Silently tolerates an already-identical message."""
    if not link.card_chat_id or not link.card_message_id:
        return
    try:
        await bot.edit_message_text(
            chat_id=link.card_chat_id,
            message_id=link.card_message_id,
            text=text,
            reply_markup=markup,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            log.debug("card edit skipped for %s: %s", link.donor_id, exc)
    except TelegramForbiddenError:
        log.debug("donor %s blocked the bot; card edit skipped", link.donor_id)


async def close_card(bot: Bot, link: DonorRequest, request: BloodRequest, note_key: str) -> None:
    """Strip the buttons and append a closing line to a card."""
    lang = settings.locale
    body = card_text(request, lang)
    await update_card(bot, link, f"{body}\n\n<i>{t(note_key, lang)}</i>", markup=None)
