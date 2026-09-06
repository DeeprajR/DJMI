"""Volunteer admin notifications (PRD 7.7, P0-12).

Every new request goes to every active admin -- scoped by district when the admin has
one -- the moment it is created, alongside the first donor wave. Each admin gets two
messages:

1. the request card with a live counter (accepted / confirmed / completed vs units),
   edited in place as numbers change and closed out on fulfilment or expiry;
2. a pre-formatted message with the deep link, meant to be forwarded as-is to a
   college group, a residents' association, a WhatsApp circle.

Admins are a manual whitelist for v1 (``scripts/add_admin.py``), per the PRD's open
question on onboarding them.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.render import card_text, fmt_day
from app.config import settings
from app.core.service import log_event
from app.enums import DonorRequestStatus, RequestStatus
from app.i18n import t
from app.models import Admin, AdminCard, BloodRequest, DonorRequest

log = logging.getLogger(__name__)


async def admins_for(session: AsyncSession, request: BloodRequest) -> list[Admin]:
    """Active admins for this district, plus those who cover every district."""
    return list(
        await session.scalars(
            select(Admin)
            .where(
                Admin.active.is_(True),
                or_(Admin.district.is_(None), Admin.district == request.district),
            )
            .order_by(Admin.telegram_user_id)
        )
    )


async def counters(session: AsyncSession, request: BloodRequest) -> dict[str, int]:
    rows = await session.execute(
        select(DonorRequest.status, func.count())
        .where(DonorRequest.request_id == request.id)
        .group_by(DonorRequest.status)
    )
    by_status = dict(rows.all())
    engaged = (
        DonorRequestStatus.ACCEPTED,
        DonorRequestStatus.SCREENING,
        DonorRequestStatus.CONFIRMED,
        DonorRequestStatus.COMPLETED,
        DonorRequestStatus.REQUEST_FILLED,
    )
    return {
        "notified": sum(by_status.values()),
        "accepted": sum(by_status.get(s, 0) for s in engaged),
        "confirmed": request.confirmed_count,
        "completed": request.completed_count,
        "waitlisted": by_status.get(DonorRequestStatus.REQUEST_FILLED, 0),
        "units": request.units_needed,
    }


def _status_line(request: BloodRequest, lang: str) -> str:
    key = {
        RequestStatus.OPEN: "admin.status_open",
        RequestStatus.FILLED: "admin.status_filled",
        RequestStatus.COMPLETED: "admin.status_completed",
        RequestStatus.CANCELLED: "admin.status_cancelled",
        RequestStatus.EXPIRED: "admin.status_expired",
    }[RequestStatus(request.status)]
    return t(key, lang)


async def admin_card_text(session: AsyncSession, request: BloodRequest, lang: str) -> str:
    c = await counters(session, request)
    return t(
        "admin.card",
        lang,
        card=card_text(request, lang),
        notified=c["notified"],
        accepted=c["accepted"],
        confirmed=c["confirmed"],
        completed=c["completed"],
        units=c["units"],
        status=_status_line(request, lang),
    )


def share_text(request: BloodRequest, lang: str) -> str:
    """The message an admin forwards. Plain text on purpose -- it survives WhatsApp."""
    return t(
        "admin.share",
        lang,
        blood_group=request.blood_group,
        units=request.units_needed,
        needed_by=fmt_day(request.needed_by),
        hospital=request.hospital_name,
        address=request.hospital_address,
        city=request.city or request.district,
        district=request.district,
        link=settings.deep_link(request.public_id),
    )


def _refresh_markup(request: BloodRequest, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("admin.refresh", lang), callback_data=f"adm:ref:{request.public_id}"
                )
            ]
        ]
    )


async def notify_admins(bot: Bot, session: AsyncSession, request: BloodRequest) -> int:
    """Send card + forwardable message to every relevant admin. Returns how many."""
    lang = settings.locale
    reached = 0
    for admin in await admins_for(session, request):
        existing = await session.scalar(
            select(AdminCard).where(
                AdminCard.request_id == request.id, AdminCard.admin_id == admin.telegram_user_id
            )
        )
        if existing is not None:
            continue  # already sent; a re-dispatch must not spam the admin
        try:
            card = await bot.send_message(
                chat_id=admin.telegram_user_id,
                text=await admin_card_text(session, request, lang),
                reply_markup=_refresh_markup(request, lang),
            )
            await bot.send_message(
                chat_id=admin.telegram_user_id,
                text=share_text(request, lang),
                disable_web_page_preview=True,
            )
        except TelegramForbiddenError:
            admin.active = False
            log.warning("admin %s has blocked the bot; deactivated", admin.telegram_user_id)
            continue
        except TelegramBadRequest as exc:
            log.warning("could not reach admin %s: %s", admin.telegram_user_id, exc)
            continue

        session.add(
            AdminCard(
                request_id=request.id,
                admin_id=admin.telegram_user_id,
                chat_id=card.chat.id,
                message_id=card.message_id,
            )
        )
        reached += 1

    await session.flush()
    await log_event(session, "admins.notified", request_id=request.id, count=reached)
    return reached


async def refresh_admin_cards(bot: Bot, session: AsyncSession, request: BloodRequest) -> None:
    """Edit every admin's card in place with the current counters and status."""
    lang = settings.locale
    text = await admin_card_text(session, request, lang)
    markup = _refresh_markup(request, lang) if request.status == RequestStatus.OPEN else None
    cards = await session.scalars(select(AdminCard).where(AdminCard.request_id == request.id))
    for card in cards:
        try:
            await bot.edit_message_text(
                chat_id=card.chat_id, message_id=card.message_id, text=text, reply_markup=markup
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc):
                log.debug("admin card edit skipped: %s", exc)
        except TelegramForbiddenError:
            pass
