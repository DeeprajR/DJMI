"""Request and donor-request state transitions.

Pure persistence -- nothing here talks to Telegram, so the rules are testable without a
bot token. Two invariants shape every function:

**Idempotency.** Telegram redelivers callback taps, and the blood bank will retry a
failed POST. Every transition is a conditional UPDATE guarded on the status it expects,
and returns what actually happened rather than assuming success. Replaying a tap is a
no-op, not a double booking.

**The last unit.** ``claim_unit`` increments ``confirmed_count`` in a single UPDATE
guarded by ``confirmed_count < units_needed``. Two donors passing screening at the same
instant contend on the same row: exactly one UPDATE matches, so one is confirmed and the
other is waitlisted (PRD 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.eligibility import next_eligible_date
from app.enums import DonorRequestStatus, RequestStatus
from app.ids import new_public_id
from app.models import BloodRequest, Donor, DonorRequest, EventLog, utcnow


def as_utc(value: datetime) -> datetime:
    """Normalise a timestamp to UTC.

    A naive value is *assumed* UTC -- that is what SQLite hands back, and what we choose
    for a bank that sends no offset. An aware value is converted, so a request stamped
    ``+05:30`` is stored and compared in the same frame as everything else.
    """
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


# --------------------------------------------------------------------------------------
# Event log (PRD 9: every state transition timestamped per request per donor)
# --------------------------------------------------------------------------------------


async def log_event(
    session: AsyncSession,
    event: str,
    *,
    donor_id: int | None = None,
    request_id: int | None = None,
    **payload: Any,
) -> None:
    session.add(
        EventLog(
            event=event,
            donor_id=donor_id,
            request_id=request_id,
            payload=payload or None,
        )
    )


# --------------------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------------------


@dataclass
class CreatedRequest:
    request: BloodRequest
    #: False when the bank retried a POST we had already accepted.
    created: bool


async def get_request_by_public_id(session: AsyncSession, public_id: str) -> BloodRequest | None:
    return await session.scalar(select(BloodRequest).where(BloodRequest.public_id == public_id))


async def create_request(session: AsyncSession, **fields: Any) -> CreatedRequest:
    """Create a request, or return the existing one for a repeated ``external_id``."""
    existing = await session.scalar(
        select(BloodRequest).where(
            BloodRequest.blood_bank_id == fields["blood_bank_id"],
            BloodRequest.external_id == fields["external_id"],
        )
    )
    if existing is not None:
        return CreatedRequest(existing, created=False)

    request = BloodRequest(public_id=await _unique_public_id(session), **fields)
    session.add(request)
    try:
        await session.flush()
    except IntegrityError:
        # Two concurrent POSTs of the same external_id; the other one won.
        await session.rollback()
        existing = await session.scalar(
            select(BloodRequest).where(
                BloodRequest.blood_bank_id == fields["blood_bank_id"],
                BloodRequest.external_id == fields["external_id"],
            )
        )
        if existing is None:
            raise
        return CreatedRequest(existing, created=False)

    await log_event(
        session,
        "request.created",
        request_id=request.id,
        blood_group=request.blood_group,
        units=request.units_needed,
        district=request.district,
    )
    return CreatedRequest(request, created=True)


async def _unique_public_id(session: AsyncSession, attempts: int = 8) -> str:
    for _ in range(attempts):
        candidate = new_public_id()
        clash = await session.scalar(
            select(BloodRequest.id).where(BloodRequest.public_id == candidate)
        )
        if clash is None:
            return candidate
    raise RuntimeError("could not allocate a unique public id")


async def close_request(
    session: AsyncSession,
    request: BloodRequest,
    status: RequestStatus,
    reason: str | None = None,
) -> bool:
    """Move a request to a terminal state. Returns False if nothing changed.

    OPEN can close to anything. FILLED -- enough donors confirmed, recruiting stopped --
    can still progress to COMPLETED once the units are actually collected; without that
    a request that filled quickly could never be marked done.
    """
    allowed = (
        [RequestStatus.OPEN, RequestStatus.FILLED]
        if status == RequestStatus.COMPLETED
        else [RequestStatus.OPEN]
    )
    result = await session.execute(
        update(BloodRequest)
        .where(BloodRequest.id == request.id, BloodRequest.status.in_(allowed))
        .values(status=status, closed_at=utcnow(), close_reason=reason, next_wave_at=None)
    )
    if result.rowcount == 0:
        return False
    await session.refresh(request)
    await log_event(
        session,
        f"request.{status.lower()}",
        request_id=request.id,
        reason=reason,
        confirmed=request.confirmed_count,
        needed=request.units_needed,
    )
    return True


# --------------------------------------------------------------------------------------
# Donor <-> request link
# --------------------------------------------------------------------------------------


async def get_donor_request(
    session: AsyncSession, request_id: int, donor_id: int
) -> DonorRequest | None:
    return await session.scalar(
        select(DonorRequest).where(
            DonorRequest.request_id == request_id, DonorRequest.donor_id == donor_id
        )
    )


async def ensure_donor_request(
    session: AsyncSession, request_id: int, donor_id: int, *, wave: int = 0
) -> tuple[DonorRequest, bool]:
    """Get or create the link row. Returns ``(row, created)``.

    Created by the wave fan-out, and also by a donor who arrives cold on a deep link
    without ever being notified.
    """
    existing = await get_donor_request(session, request_id, donor_id)
    if existing is not None:
        return existing, False

    link = DonorRequest(
        request_id=request_id,
        donor_id=donor_id,
        wave=wave,
        status=DonorRequestStatus.NOTIFIED,
        notified_at=utcnow(),
    )
    session.add(link)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await get_donor_request(session, request_id, donor_id)
        if existing is None:
            raise
        return existing, False
    return link, True


async def set_answers(session: AsyncSession, link: DonorRequest, answers: dict[str, bool]) -> None:
    """Persist questionnaire progress without changing status."""
    await session.execute(
        update(DonorRequest).where(DonorRequest.id == link.id).values(answers=answers)
    )
    await session.refresh(link)


async def transition(
    session: AsyncSession,
    link: DonorRequest,
    to_status: DonorRequestStatus,
    *,
    expected: tuple[DonorRequestStatus, ...],
    **values: Any,
) -> bool:
    """Conditional state move. False means a duplicate tap or an out-of-order update.

    The caller should re-render from the row's real status rather than treating False as
    an error -- the donor cannot tell that Telegram delivered their tap twice.
    """
    result = await session.execute(
        update(DonorRequest)
        .where(
            DonorRequest.id == link.id,
            DonorRequest.status.in_([s.value for s in expected]),
        )
        .values(status=to_status, **values)
    )
    if result.rowcount == 0:
        await session.refresh(link)
        return False
    await session.refresh(link)
    await log_event(
        session,
        f"donor_request.{to_status.lower()}",
        donor_id=link.donor_id,
        request_id=link.request_id,
    )
    return True


# --------------------------------------------------------------------------------------
# The last unit
# --------------------------------------------------------------------------------------


class ConfirmOutcome(StrEnum):
    CONFIRMED = "CONFIRMED"
    #: Passed screening but the units were already met -- placed on the waitlist.
    WAITLISTED = "WAITLISTED"
    #: The tap was a replay; the row was already in a terminal state.
    ALREADY_HANDLED = "ALREADY_HANDLED"
    REQUEST_CLOSED = "REQUEST_CLOSED"


@dataclass
class ConfirmResult:
    outcome: ConfirmOutcome
    request: BloodRequest
    link: DonorRequest
    #: True when this confirmation was the one that met the requirement.
    just_filled: bool = False


async def claim_unit(session: AsyncSession, request_id: int) -> bool:
    """Atomically take one unit if the request is open and units remain.

    The guard lives in the WHERE clause, so the database -- not application logic --
    decides who gets the last unit.
    """
    result = await session.execute(
        update(BloodRequest)
        .where(
            BloodRequest.id == request_id,
            BloodRequest.status == RequestStatus.OPEN,
            BloodRequest.confirmed_count < BloodRequest.units_needed,
        )
        .values(confirmed_count=BloodRequest.confirmed_count + 1)
    )
    return result.rowcount == 1


async def release_unit(session: AsyncSession, request_id: int) -> None:
    """Give a unit back (donor cancelled, or a claim we could not use)."""
    await session.execute(
        update(BloodRequest)
        .where(BloodRequest.id == request_id, BloodRequest.confirmed_count > 0)
        .values(confirmed_count=BloodRequest.confirmed_count - 1)
    )


async def confirm_or_waitlist(
    session: AsyncSession, link: DonorRequest, request: BloodRequest
) -> ConfirmResult:
    """Resolve a donor who has just passed screening (PRD P0-7).

    Claim first, then move the donor row. If the donor row will not move -- a duplicate
    tap -- the claim is released, so a replay cannot consume a second unit.
    """
    claimed = await claim_unit(session, request.id)

    if claimed:
        moved = await transition(
            session,
            link,
            DonorRequestStatus.CONFIRMED,
            expected=(DonorRequestStatus.SCREENING, DonorRequestStatus.ACCEPTED),
            confirmed_at=utcnow(),
        )
        if not moved:
            await release_unit(session, request.id)
            await session.refresh(request)
            return ConfirmResult(ConfirmOutcome.ALREADY_HANDLED, request, link)

        await session.refresh(request)
        just_filled = request.confirmed_count >= request.units_needed
        if just_filled:
            await close_request(session, request, RequestStatus.FILLED, "units met")
        return ConfirmResult(ConfirmOutcome.CONFIRMED, request, link, just_filled=just_filled)

    # No unit available: either the request closed or someone else took the last one.
    await session.refresh(request)
    moved = await transition(
        session,
        link,
        DonorRequestStatus.REQUEST_FILLED,
        expected=(DonorRequestStatus.SCREENING, DonorRequestStatus.ACCEPTED),
        waitlisted_at=utcnow(),
    )
    if not moved:
        return ConfirmResult(ConfirmOutcome.ALREADY_HANDLED, request, link)
    outcome = (
        ConfirmOutcome.WAITLISTED
        if request.status in (RequestStatus.OPEN, RequestStatus.FILLED)
        else ConfirmOutcome.REQUEST_CLOSED
    )
    return ConfirmResult(outcome, request, link)


# --------------------------------------------------------------------------------------
# Completion (blood bank reports a collected unit)
# --------------------------------------------------------------------------------------


@dataclass
class CompletionResult:
    link: DonorRequest
    donor: Donor
    request: BloodRequest
    next_eligible: date
    #: False when this completion was already recorded.
    recorded: bool


async def mark_completed(
    session: AsyncSession,
    link: DonorRequest,
    donated_on: date,
) -> CompletionResult:
    """Record a collected donation and roll the donor's cooldown forward (P0-11).

    Accepts a donation from any state except an already-recorded one. The blood bank is
    the authority on who actually gave blood -- a donor who walked in without confirming,
    or off the waitlist, still needs an accurate cooldown, and PRD goal 4 hangs on that.
    """
    donor = await session.get(Donor, link.donor_id)
    request = await session.get(BloodRequest, link.request_id)
    assert donor is not None and request is not None

    moved = await transition(
        session,
        link,
        DonorRequestStatus.COMPLETED,
        expected=tuple(s for s in DonorRequestStatus if s is not DonorRequestStatus.COMPLETED),
        completed_at=utcnow(),
    )
    if moved:
        request.completed_count += 1
        if donor.last_donation_date is None or donor.last_donation_date < donated_on:
            donor.last_donation_date = donated_on
        # A completed donation is a typing event -- the group on file is now confirmed.
        donor.blood_group_verified = True
        await session.flush()

    return CompletionResult(
        link=link,
        donor=donor,
        request=request,
        next_eligible=next_eligible_date(donor.last_donation_date or donated_on, donor.sex),
        recorded=moved,
    )


# --------------------------------------------------------------------------------------
# Waitlist
# --------------------------------------------------------------------------------------


async def waitlisted_donors(session: AsyncSession, request_id: int) -> list[DonorRequest]:
    """Donors who passed screening after the units were met, oldest first."""
    result = await session.scalars(
        select(DonorRequest)
        .where(
            DonorRequest.request_id == request_id,
            DonorRequest.status == DonorRequestStatus.REQUEST_FILLED,
        )
        .order_by(DonorRequest.waitlisted_at.asc())
    )
    return list(result)


async def pending_donors(session: AsyncSession, request_id: int) -> list[DonorRequest]:
    """Donors still holding an unanswered card, so it can be edited when things change."""
    result = await session.scalars(
        select(DonorRequest).where(
            DonorRequest.request_id == request_id,
            DonorRequest.status.in_(
                [
                    DonorRequestStatus.NOTIFIED,
                    DonorRequestStatus.ACCEPTED,
                    DonorRequestStatus.SCREENING,
                ]
            ),
        )
    )
    return list(result)


def schedule_next_wave(request: BloodRequest, interval_minutes: int) -> None:
    request.next_wave_at = utcnow() + timedelta(minutes=interval_minutes)


def clamp_to_needed_by(request: BloodRequest) -> None:
    """Never schedule a wave after the blood is no longer useful.

    Both sides go through ``as_utc``: a value just set in Python is timezone-aware, while
    one reloaded from SQLite comes back naive.
    """
    if request.next_wave_at and as_utc(request.next_wave_at) > as_utc(request.needed_by):
        request.next_wave_at = None
