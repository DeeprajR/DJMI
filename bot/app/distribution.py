"""Wave-based fan-out (PRD 7.5, P0-5).

Eligible donors are notified in waves of ``WAVE_SIZE``, nearest city first and
longest-since-last-donation first, escalating every ``WAVE_INTERVAL_MINUTES`` only while
the requirement is still short. The moment confirmations meet the units needed, waves
stop and every unanswered card is closed -- a donor should never walk into a hospital
for a request that no longer needs them.

Scheduling is a database column (``next_wave_at``) polled by a ticker rather than an
in-memory timer, so a restart mid-request resumes the escalation instead of stranding it.
"""

from __future__ import annotations

import logging
from datetime import date

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.admin import notify_admins, refresh_admin_cards
from app.bot.render import close_card, deliver_card
from app.config import settings
from app.core.eligibility import eligible_donors_query
from app.core.service import (
    as_utc,
    clamp_to_needed_by,
    close_request,
    ensure_donor_request,
    log_event,
    pending_donors,
    schedule_next_wave,
)
from app.db import session_scope
from app.enums import RequestStatus
from app.integration.demand import report_progress
from app.integration.demand import sync as bank_sync
from app.models import BloodRequest, utcnow

log = logging.getLogger(__name__)


async def run_wave(bot: Bot, session: AsyncSession, request: BloodRequest) -> int:
    """Notify the next wave for ``request``. Returns how many donors were reached."""
    if request.status != RequestStatus.OPEN:
        return 0

    if request.confirmed_count >= request.units_needed:
        await fill_request(bot, session, request)
        return 0

    if as_utc(request.needed_by) <= utcnow():
        await expire_request(bot, session, request)
        return 0

    donors = list(
        await session.scalars(
            eligible_donors_query(request, date.today(), limit=settings.wave_size)
        )
    )

    reached = 0
    for donor in donors:
        link, created = await ensure_donor_request(
            session, request.id, donor.telegram_user_id, wave=request.wave_index
        )
        if not created:
            continue
        if await deliver_card(bot, session, donor, request, link):
            reached += 1
        else:
            # Blocked or rate-limited: drop the link so a later wave can retry them.
            await session.delete(link)

    request.wave_index += 1
    schedule_next_wave(request, settings.wave_interval_minutes)
    clamp_to_needed_by(request)
    await session.flush()
    await publish_state(bot, session, request)

    await log_event(
        session,
        "request.wave_sent",
        request_id=request.id,
        wave=request.wave_index,
        reached=reached,
        candidates=len(donors),
    )
    log.info(
        "request %s wave %s: %s/%s donors reached",
        request.public_id,
        request.wave_index,
        reached,
        len(donors),
    )
    return reached


async def dispatch_new_request(bot: Bot, session: AsyncSession, request: BloodRequest) -> int:
    """First wave plus the admin cards, the moment a request lands."""
    reached = await run_wave(bot, session, request)
    await notify_admins(bot, session, request)
    return reached


async def publish_state(bot: Bot, session: AsyncSession, request: BloodRequest) -> None:
    """Push the request's current numbers everywhere that mirrors them."""
    await refresh_admin_cards(bot, session, request)
    await report_progress(session, request)


async def fill_request(bot: Bot, session: AsyncSession, request: BloodRequest) -> None:
    """Requirement met: stop the waves and close every unanswered card."""
    if await close_request(session, request, RequestStatus.FILLED, "units met"):
        await close_pending_cards(bot, session, request, "confirmation.card_filled")
        await publish_state(bot, session, request)


async def expire_request(bot: Bot, session: AsyncSession, request: BloodRequest) -> None:
    if await close_request(session, request, RequestStatus.EXPIRED, "needed_by passed"):
        await close_pending_cards(bot, session, request, "confirmation.card_expired")
        await publish_state(bot, session, request)


async def close_pending_cards(
    bot: Bot, session: AsyncSession, request: BloodRequest, note_key: str
) -> None:
    """Edit out the Accept button on cards nobody answered."""
    for link in await pending_donors(session, request.id):
        await close_card(bot, link, request, note_key)


async def tick(bot: Bot) -> None:
    """One scheduler pass: pull bank demand, escalate due waves, expire stale requests."""
    now = utcnow()
    async with session_scope() as session:
        if settings.bank_sync_enabled:
            await bank_sync(bot, session)

        due = list(
            await session.scalars(
                select(BloodRequest).where(
                    BloodRequest.status == RequestStatus.OPEN,
                    BloodRequest.next_wave_at.is_not(None),
                    BloodRequest.next_wave_at <= now,
                )
            )
        )
        for request in due:
            await run_wave(bot, session, request)

        stale = list(
            await session.scalars(
                select(BloodRequest).where(
                    BloodRequest.status == RequestStatus.OPEN,
                    BloodRequest.needed_by <= now,
                )
            )
        )
        for request in stale:
            await expire_request(bot, session, request)
