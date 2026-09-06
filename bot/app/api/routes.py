"""Inbound API: the blood bank's only way to reach the donor pool (PRD P0-1).

Demand originates here and nowhere else -- nobody can raise a request from inside the
bot, which is what keeps every card a donor sees verified by the bank (PRD 4).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.auth import verify_signature
from app.api.schemas import (
    CloseIn,
    CompletionResultOut,
    CompletionsIn,
    CompletionsOut,
    RequestIn,
    RequestOut,
)
from app.config import settings
from app.core.service import (
    as_utc,
    close_request,
    create_request,
    get_donor_request,
    get_request_by_public_id,
    log_event,
    mark_completed,
)
from app.db import session_scope
from app.distribution import close_pending_cards, dispatch_new_request
from app.enums import DonorRequestStatus, RequestStatus
from app.i18n import t
from app.models import BloodRequest, Donor, DonorRequest

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["blood-bank"])


def _to_out(request: BloodRequest, created: bool = True) -> RequestOut:
    return RequestOut(
        public_id=request.public_id,
        status=RequestStatus(request.status),
        blood_group=request.blood_group,
        units_needed=request.units_needed,
        confirmed_count=request.confirmed_count,
        completed_count=request.completed_count,
        deep_link=settings.deep_link(request.public_id),
        # Stored naive on SQLite; the bank always receives an explicit UTC offset.
        needed_by=as_utc(request.needed_by),
        created=created,
    )


@router.post("/requests", response_model=RequestOut, status_code=status.HTTP_201_CREATED)
async def create(
    payload: RequestIn,
    http_request: Request,
    blood_bank_id: str = Depends(verify_signature),
) -> RequestOut:
    """Accept demand and start distribution immediately.

    Retrying the same ``external_id`` returns the original request with
    ``created: false`` instead of fanning out a second time.
    """
    needed_by = as_utc(payload.needed_by)
    if needed_by <= datetime.now(UTC):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "needed_by is already past")

    bot = http_request.app.state.bot
    async with session_scope() as session:
        result = await create_request(
            session,
            blood_bank_id=blood_bank_id,
            external_id=payload.external_id,
            blood_group=payload.blood_group,
            exact_match=payload.exact_match,
            units_needed=payload.units_needed,
            hospital_name=payload.hospital.name,
            hospital_address=payload.hospital.address,
            district=payload.district,
            city=payload.city,
            needed_by=needed_by,
            slot_time=as_utc(payload.slot_time) if payload.slot_time else None,
            notes=payload.notes,
        )
        if result.created:
            await dispatch_new_request(bot, session, result.request)
        return _to_out(result.request, created=result.created)


@router.get("/requests/{public_id}", response_model=RequestOut)
async def read(
    public_id: str,
    blood_bank_id: str = Depends(verify_signature),
) -> RequestOut:
    async with session_scope() as session:
        request = await _load(session, public_id, blood_bank_id)
        return _to_out(request)


@router.post("/requests/{public_id}/close", response_model=RequestOut)
async def close(
    public_id: str,
    payload: CloseIn,
    http_request: Request,
    blood_bank_id: str = Depends(verify_signature),
) -> RequestOut:
    """Withdraw or finish a request; unanswered donor cards are closed with it."""
    bot = http_request.app.state.bot
    async with session_scope() as session:
        request = await _load(session, public_id, blood_bank_id)
        closed = await close_request(session, request, payload.status, payload.reason)
        if closed:
            note = (
                "confirmation.card_expired"
                if payload.status == RequestStatus.CANCELLED
                else "confirmation.card_filled"
            )
            await close_pending_cards(bot, session, request, note)
        return _to_out(request, created=False)


@router.post("/requests/{public_id}/completions", response_model=CompletionsOut)
async def complete(
    public_id: str,
    payload: CompletionsIn,
    http_request: Request,
    blood_bank_id: str = Depends(verify_signature),
) -> CompletionsOut:
    """Report collected donations, updating each donor's cooldown and thanking them."""
    bot = http_request.app.state.bot
    results: list[CompletionResultOut] = []

    async with session_scope() as session:
        request = await _load(session, public_id, blood_bank_id)

        for item in payload.donations:
            donor = await _find_donor(session, item.telegram_user_id, item.phone)
            if donor is None:
                results.append(
                    CompletionResultOut(donor_id=None, recorded=False, detail="donor not found")
                )
                continue

            link = await get_donor_request(session, request.id, donor.telegram_user_id)
            if link is None:
                results.append(
                    CompletionResultOut(
                        donor_id=donor.telegram_user_id,
                        recorded=False,
                        detail="donor was not part of this request",
                    )
                )
                continue

            if item.blood_group:
                # The bank typed them on site; an "I don't know" donor is now matchable.
                donor.blood_group = item.blood_group
                donor.blood_group_verified = True

            outcome = await mark_completed(session, link, item.donated_at)
            results.append(
                CompletionResultOut(
                    donor_id=donor.telegram_user_id,
                    recorded=outcome.recorded,
                    detail="recorded" if outcome.recorded else "already recorded",
                )
            )

            if outcome.recorded:
                await _thank(bot, donor, request, outcome.next_eligible)

        await session.refresh(request)
        if request.completed_count >= request.units_needed:
            await close_request(session, request, RequestStatus.COMPLETED, "all units collected")

        await log_event(
            session,
            "request.completions_reported",
            request_id=request.id,
            count=len(payload.donations),
        )
        return CompletionsOut(
            public_id=request.public_id,
            completed_count=request.completed_count,
            results=results,
        )


async def _thank(bot, donor: Donor, request: BloodRequest, next_eligible) -> None:
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
    except Exception as exc:  # noqa: BLE001 - a blocked donor must not fail the bank's call
        log.warning("could not thank donor %s: %s", donor.telegram_user_id, exc)


async def _find_donor(session, telegram_user_id: int | None, phone: str | None) -> Donor | None:
    if telegram_user_id:
        donor = await session.get(Donor, telegram_user_id)
        if donor is not None:
            return donor
    if phone:
        normalised = "+" + "".join(ch for ch in phone if ch.isdigit())
        return await session.scalar(select(Donor).where(Donor.phone == normalised))
    return None


async def _load(session, public_id: str, blood_bank_id: str) -> BloodRequest:
    request = await get_request_by_public_id(session, public_id.upper())
    if request is None or request.blood_bank_id != blood_bank_id:
        # Same 404 either way: a bank must not be able to probe another bank's ids.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "request not found")
    return request


@router.get("/requests/{public_id}/donors", tags=["blood-bank"])
async def confirmed_donors(
    public_id: str,
    blood_bank_id: str = Depends(verify_signature),
) -> dict:
    """Who to expect at the counter: confirmed donors with their verified numbers.

    This is the one place donor contact details leave the bot, and only ever to the
    blood bank that raised the request.
    """
    async with session_scope() as session:
        request = await _load(session, public_id, blood_bank_id)
        rows = await session.execute(
            select(Donor, DonorRequest)
            .join(DonorRequest, DonorRequest.donor_id == Donor.telegram_user_id)
            .where(
                DonorRequest.request_id == request.id,
                DonorRequest.status.in_(
                    [DonorRequestStatus.CONFIRMED, DonorRequestStatus.COMPLETED]
                ),
            )
            .order_by(DonorRequest.confirmed_at.asc())
        )
        return {
            "public_id": request.public_id,
            "donors": [
                {
                    "telegram_user_id": donor.telegram_user_id,
                    "name": donor.full_name,
                    "phone": donor.phone,
                    "blood_group": donor.blood_group,
                    "status": link.status,
                    "confirmed_at": as_utc(link.confirmed_at) if link.confirmed_at else None,
                }
                for donor, link in rows.all()
            ],
        }
