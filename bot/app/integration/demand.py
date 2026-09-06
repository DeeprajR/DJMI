"""Shared-database integration with the blood bank dashboard (Module 2).

The bank and the bot share one Postgres. Two tables in the ``public`` schema are the
entire contract (their Drizzle definitions live in the hospital repo,
``src/db/schema/blood-bank.ts``):

``donor_demand``
    Created by the bank when a request cannot be met from stock or a group drops
    below its floor. The bot imports rows with ``status = 'open'`` and no
    ``bot_public_id`` yet, starts distribution, and writes progress back into the
    ``*_units`` columns and ``status``.

``donor_demand_confirmations``
    One row per donor the bot has confirmed -- the roster the counter works from.
    The bank marks a row ``completed`` with ``donated_at`` when the person gives
    blood (or ``no_show`` / ``cancelled``); the bot acknowledges it, updates the
    donor's cooldown and sends the thank-you.

Only the columns the bot touches are declared here, as SQLAlchemy Core tables in a
separate ``MetaData`` with no schema, so they resolve to ``public.*`` on Postgres and to
plain tables on SQLite in tests. The bot never creates them on Postgres; the bank's
migrations do.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Enum,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.render import close_card
from app.config import settings
from app.core.service import (
    close_request,
    create_request,
    get_donor_request,
    mark_completed,
    pending_donors,
    release_unit,
    transition,
)
from app.enums import DonorRequestStatus, RequestStatus
from app.i18n import t
from app.models import BloodRequest, Donor, DonorRequest, utcnow

log = logging.getLogger(__name__)

shared = MetaData()


def _pg_enum(name: str, *values: str) -> Enum:
    """A Postgres enum the bank's migrations own.

    Declared as an Enum, not a String, so bound parameters are cast to the enum type
    (``$1::demand_status``); Postgres has no ``enum = varchar`` operator and would
    reject a plain string. ``create_type=False`` because the type already exists;
    on SQLite (tests) this degrades to a plain VARCHAR.
    """
    return Enum(*values, name=name, native_enum=True, create_type=False, create_constraint=False)


BLOOD_GROUP = _pg_enum("blood_group", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")
BLOOD_PRODUCT = _pg_enum(
    "blood_product",
    "whole_blood",
    "packed_rbc",
    "platelet",
    "fresh_frozen_plasma",
    "cryopresipitate",
)
DEMAND_TRIGGER = _pg_enum("demand_trigger", "request_shortfall", "stock_floor")
DEMAND_STATUS = _pg_enum("demand_status", "open", "fulfilled", "completed", "cancelled", "expired")
CONFIRMATION_STATUS = _pg_enum(
    "confirmation_status", "confirmed", "completed", "cancelled", "no_show"
)

#: Postgres `uuid` columns. `as_uuid=False` keeps them plain strings on both dialects,
#: which is what the bot stores in `BloodRequest.demand_id`.
UUID_STR = Uuid(as_uuid=False)

donor_demand = Table(
    "donor_demand",
    shared,
    Column("id", UUID_STR, primary_key=True),
    Column("trigger", DEMAND_TRIGGER),
    Column("blood_request_id", UUID_STR),
    Column("blood_group", BLOOD_GROUP, nullable=False),
    Column("product", BLOOD_PRODUCT),
    Column("units", Integer, nullable=False),
    Column("date_needed", Date, nullable=False),
    Column("hospital_name", Text, nullable=False),
    Column("hospital_address", Text, nullable=False),
    Column("district", Text, nullable=False),
    Column("city", Text, nullable=False),
    Column("notes", Text),
    Column("status", DEMAND_STATUS, nullable=False),
    Column("bot_public_id", String(16)),
    Column("bot_imported_at", DateTime(timezone=True)),
    Column("confirmed_units", Integer),
    Column("waitlisted_units", Integer),
    Column("completed_units", Integer),
    Column("notified_donors", Integer),
    Column("updated_at", DateTime(timezone=True)),
    Column("closed_at", DateTime(timezone=True)),
)

donor_demand_confirmations = Table(
    "donor_demand_confirmations",
    shared,
    Column("id", UUID_STR, primary_key=True),
    Column("demand_id", UUID_STR, nullable=False),
    Column("telegram_user_id", BigInteger, nullable=False),
    Column("donor_name", Text),
    Column("donor_phone", Text),
    Column("blood_group", BLOOD_GROUP),
    Column("status", CONFIRMATION_STATUS, nullable=False),
    Column("confirmed_at", DateTime(timezone=True)),
    Column("donated_at", Date),
    Column("bag_rfid_tag", Text),
    Column("bot_acknowledged_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)

#: Bot request status -> what the bank's dashboard shows.
_STATUS_TO_BANK = {
    RequestStatus.OPEN: "open",
    RequestStatus.FILLED: "fulfilled",
    RequestStatus.COMPLETED: "completed",
    RequestStatus.CANCELLED: "cancelled",
    RequestStatus.EXPIRED: "expired",
}


def _local_tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.display_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def needed_by_from_date(day: date) -> datetime:
    """The bank records a *day*; donors are told to come any time before it ends."""
    return datetime.combine(day, time(23, 59), tzinfo=_local_tz()).astimezone(ZoneInfo("UTC"))


# --------------------------------------------------------------------------------------
# Bank -> bot: new demand
# --------------------------------------------------------------------------------------


async def import_open_demands(bot: Bot, session: AsyncSession) -> int:
    """Turn every unclaimed open demand row into a bot request and start distribution."""
    from app.distribution import dispatch_new_request

    rows = (
        await session.execute(
            select(donor_demand).where(
                donor_demand.c.status == "open",
                donor_demand.c.bot_public_id.is_(None),
            )
        )
    ).mappings()

    imported = 0
    for row in rows:
        result = await create_request(
            session,
            blood_bank_id=settings.bank_id,
            external_id=str(row["id"]),
            demand_id=str(row["id"]),
            blood_group=row["blood_group"],
            exact_match=False,
            units_needed=row["units"],
            hospital_name=row["hospital_name"],
            hospital_address=row["hospital_address"],
            district=row["district"],
            city=row["city"],
            needed_by=needed_by_from_date(row["date_needed"]),
            slot_time=None,
            notes=row["notes"],
        )
        request = result.request
        await session.execute(
            update(donor_demand)
            .where(donor_demand.c.id == row["id"])
            .values(bot_public_id=request.public_id, bot_imported_at=utcnow(), updated_at=utcnow())
        )
        if result.created:
            await dispatch_new_request(bot, session, request)
            await report_progress(session, request)
            imported += 1
            log.info("imported bank demand %s as request %s", row["id"], request.public_id)

    return imported


# --------------------------------------------------------------------------------------
# Bot -> bank: progress and roster
# --------------------------------------------------------------------------------------


async def report_progress(session: AsyncSession, request: BloodRequest) -> None:
    """Mirror the request's counters and status onto its demand row."""
    if not request.demand_id:
        return
    await session.refresh(request)
    links = list(
        await session.scalars(select(DonorRequest).where(DonorRequest.request_id == request.id))
    )
    waitlisted = sum(1 for link in links if link.status == DonorRequestStatus.REQUEST_FILLED)
    values: dict[str, Any] = {
        "confirmed_units": request.confirmed_count,
        "waitlisted_units": waitlisted,
        "completed_units": request.completed_count,
        "notified_donors": len(links),
        "status": _STATUS_TO_BANK[RequestStatus(request.status)],
        "updated_at": utcnow(),
    }
    if request.status != RequestStatus.OPEN:
        values["closed_at"] = request.closed_at or utcnow()
    await session.execute(
        update(donor_demand).where(donor_demand.c.id == request.demand_id).values(**values)
    )


async def record_confirmation(session: AsyncSession, request: BloodRequest, donor: Donor) -> None:
    """Add a confirmed donor to the bank's roster. Idempotent per (demand, donor)."""
    if not request.demand_id:
        return
    exists = await session.scalar(
        select(donor_demand_confirmations.c.id).where(
            donor_demand_confirmations.c.demand_id == request.demand_id,
            donor_demand_confirmations.c.telegram_user_id == donor.telegram_user_id,
        )
    )
    if exists:
        return
    import uuid

    now = utcnow()
    await session.execute(
        donor_demand_confirmations.insert().values(
            id=str(uuid.uuid4()),
            demand_id=request.demand_id,
            telegram_user_id=donor.telegram_user_id,
            donor_name=donor.full_name,
            donor_phone=donor.phone,
            blood_group=donor.blood_group,
            status="confirmed",
            confirmed_at=now,
            created_at=now,
            updated_at=now,
        )
    )


async def withdraw_confirmation(
    session: AsyncSession, request: BloodRequest, donor_id: int, status: str
) -> None:
    """The donor cancelled or was marked no-show on the bot side; reflect it on the roster."""
    if not request.demand_id:
        return
    await session.execute(
        update(donor_demand_confirmations)
        .where(
            donor_demand_confirmations.c.demand_id == request.demand_id,
            donor_demand_confirmations.c.telegram_user_id == donor_id,
            donor_demand_confirmations.c.status == "confirmed",
        )
        .values(status=status, updated_at=utcnow())
    )


# --------------------------------------------------------------------------------------
# Bank -> bot: what happened at the counter
# --------------------------------------------------------------------------------------


async def acknowledge_counter_updates(bot: Bot, session: AsyncSession) -> int:
    """Apply the bank's marks (donated / no-show / cancelled) that the bot has not seen."""
    rows = (
        await session.execute(
            select(donor_demand_confirmations, donor_demand.c.bot_public_id)
            .join(donor_demand, donor_demand.c.id == donor_demand_confirmations.c.demand_id)
            .where(
                donor_demand_confirmations.c.status.in_(["completed", "no_show", "cancelled"]),
                donor_demand_confirmations.c.bot_acknowledged_at.is_(None),
            )
        )
    ).mappings()

    handled = 0
    for row in rows:
        request = await session.scalar(
            select(BloodRequest).where(BloodRequest.demand_id == row["demand_id"])
        )
        if request is None:
            continue
        link = await get_donor_request(session, request.id, row["telegram_user_id"])
        if link is not None:
            if row["status"] == "completed":
                donated_on = row["donated_at"] or date.today()
                outcome = await mark_completed(session, link, donated_on)
                if outcome.recorded:
                    await _thank(bot, outcome.donor, request, outcome.next_eligible)
            elif row["status"] == "no_show":
                await transition(
                    session,
                    link,
                    DonorRequestStatus.NO_SHOW,
                    expected=(DonorRequestStatus.CONFIRMED,),
                )
            elif row["status"] == "cancelled":
                moved = await transition(
                    session,
                    link,
                    DonorRequestStatus.CANCELLED,
                    expected=(DonorRequestStatus.CONFIRMED,),
                )
                if moved:
                    await release_unit(session, request.id)

        await session.execute(
            update(donor_demand_confirmations)
            .where(donor_demand_confirmations.c.id == row["id"])
            .values(bot_acknowledged_at=utcnow())
        )
        await session.refresh(request)
        if request.completed_count >= request.units_needed:
            await close_request(session, request, RequestStatus.COMPLETED, "all units collected")
        await report_progress(session, request)
        handled += 1

    return handled


async def apply_bank_cancellations(bot: Bot, session: AsyncSession) -> int:
    """The bank withdrew a demand (stock arrived, patient discharged): stop recruiting."""
    rows = (
        await session.execute(
            select(donor_demand.c.id, donor_demand.c.status).where(
                donor_demand.c.status.in_(["cancelled", "completed"]),
                donor_demand.c.bot_public_id.is_not(None),
            )
        )
    ).mappings()

    closed = 0
    for row in rows:
        request = await session.scalar(
            select(BloodRequest).where(
                BloodRequest.demand_id == row["id"], BloodRequest.status == RequestStatus.OPEN
            )
        )
        if request is None:
            continue
        status = (
            RequestStatus.CANCELLED if row["status"] == "cancelled" else RequestStatus.COMPLETED
        )
        if await close_request(session, request, status, f"bank marked {row['status']}"):
            for link in await pending_donors(session, request.id):
                await close_card(bot, link, request, "confirmation.card_expired")
            closed += 1
    return closed


async def sync(bot: Bot, session: AsyncSession) -> None:
    """One pass of everything, called from the ticker."""
    await import_open_demands(bot, session)
    await acknowledge_counter_updates(bot, session)
    await apply_bank_cancellations(bot, session)


async def _thank(bot: Bot, donor: Donor, request: BloodRequest, next_eligible: date) -> None:
    try:
        await bot.send_message(
            chat_id=donor.telegram_user_id,
            text=t(
                "completion.thanks",
                donor.language,
                hospital=request.hospital_name,
                next_date=next_eligible.strftime("%d %b %Y"),
            ),
        )
    except Exception as exc:  # noqa: BLE001 - a blocked donor must not stall the sync
        log.warning("could not thank donor %s: %s", donor.telegram_user_id, exc)
