"""Persistence model.

Design notes carried from the PRD:
- Donor PK is the Telegram user_id; phone is a *verified attribute*, not identity (PRD 12).
- ``BloodRequest.confirmed_count`` is denormalised so the last unit can be claimed with a
  single conditional UPDATE -- that is the concurrency guard from PRD 12.
- ``(blood_bank_id, external_id)`` is unique so a retried POST /requests is idempotent.
- Every state transition is appended to ``event_log`` for the metrics in PRD 9.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.config import settings
from app.enums import BloodGroup, DonorRequestStatus, RequestStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    # A schema-qualified MetaData also resolves the string ForeignKey targets below
    # within that schema, so `donors.telegram_user_id` means `donor_bot.donors...`.
    metadata = MetaData(schema=settings.db_schema)
    type_annotation_map = {dict: JSON, list: JSON}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now()
    )


class Donor(Base, TimestampMixin):
    __tablename__ = "donors"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(120))
    dob: Mapped[date | None] = mapped_column(Date)
    sex: Mapped[str | None] = mapped_column(String(1))
    blood_group: Mapped[str] = mapped_column(String(8), default=BloodGroup.UNKNOWN)
    #: True once staff typed the donor at a donation. UNKNOWN donors are never matched (7.4).
    blood_group_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    district: Mapped[str | None] = mapped_column(String(80), index=True)
    city: Mapped[str | None] = mapped_column(String(80))

    last_donation_date: Mapped[date | None] = mapped_column(Date)

    #: Onboarding finished -- partial records exist while the FSM is mid-flight.
    is_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snoozed_until: Mapped[date | None] = mapped_column(Date)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Set when a questionnaire answer looks permanent rather than temporary (7.6).
    review_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str | None] = mapped_column(String(200))

    #: Attribution: the request whose deep link brought this donor in (P1 analytics).
    source_request_id: Mapped[int | None] = mapped_column(ForeignKey("blood_requests.id"))

    language: Mapped[str] = mapped_column(String(5), default="en")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Donor {self.telegram_user_id} {self.blood_group} {self.district}>"


class BloodRequest(Base, TimestampMixin):
    __tablename__ = "blood_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: Short id used in the deep link ``?start=req_<public_id>`` (PRD 12).
    public_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)

    #: Multi-tenant from day one even though v1 runs one bank (PRD 8, P2).
    blood_bank_id: Mapped[str] = mapped_column(String(64), index=True)
    #: The identifier supplied by the bank; makes POST /requests idempotent on retry.
    external_id: Mapped[str] = mapped_column(String(64))
    #: Row id in the shared `public.donor_demand` table when the request came from the
    #: blood bank dashboard rather than the HTTP API. Progress is reported back to it.
    demand_id: Mapped[str | None] = mapped_column(String(36), index=True)

    blood_group: Mapped[str] = mapped_column(String(8))
    #: Bank may demand the exact group instead of the compatibility matrix.
    exact_match: Mapped[bool] = mapped_column(Boolean, default=False)

    units_needed: Mapped[int] = mapped_column(Integer)
    confirmed_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)

    hospital_name: Mapped[str] = mapped_column(String(160))
    hospital_address: Mapped[str] = mapped_column(Text)
    district: Mapped[str] = mapped_column(String(80), index=True)
    city: Mapped[str | None] = mapped_column(String(80))

    needed_by: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: Optional bank-assigned appointment time; absent means "arrive before needed_by".
    slot_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(16), default=RequestStatus.OPEN, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(200))

    # Wave fan-out bookkeeping (7.5)
    wave_index: Mapped[int] = mapped_column(Integer, default=0)
    next_wave_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    donor_links: Mapped[list[DonorRequest]] = relationship(back_populates="request")

    __table_args__ = (
        UniqueConstraint("blood_bank_id", "external_id", name="uq_bank_external_id"),
        Index("ix_request_open_district", "status", "district"),
    )

    @property
    def units_remaining(self) -> int:
        return max(0, self.units_needed - self.confirmed_count)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<BloodRequest {self.public_id} {self.blood_group} "
            f"{self.confirmed_count}/{self.units_needed}>"
        )


class DonorRequest(Base, TimestampMixin):
    """One donor journey through one request (PRD 7.2)."""

    __tablename__ = "donor_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("blood_requests.id"), index=True)
    donor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("donors.telegram_user_id"), index=True
    )

    status: Mapped[str] = mapped_column(String(20), default=DonorRequestStatus.NOTIFIED, index=True)
    wave: Mapped[int] = mapped_column(Integer, default=0)

    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    waitlisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Card message we edit in place instead of spamming new messages (PRD 12).
    card_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    card_message_id: Mapped[int | None] = mapped_column(BigInteger)

    #: Answers keyed by question id, plus the question that ended the flow.
    answers: Mapped[dict | None] = mapped_column(JSON)
    eliminated_reason: Mapped[str | None] = mapped_column(String(120))

    request: Mapped[BloodRequest] = relationship(back_populates="donor_links")
    donor: Mapped[Donor] = relationship()

    __table_args__ = (
        UniqueConstraint("request_id", "donor_id", name="uq_donor_per_request"),
        Index("ix_dr_request_status", "request_id", "status"),
    )


class Admin(Base, TimestampMixin):
    """Volunteer admin. v1 whitelist is manual (Open Question: Ops)."""

    __tablename__ = "admins"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str | None] = mapped_column(String(120))
    #: NULL = receives every district's requests.
    district: Mapped[str | None] = mapped_column(String(80), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class FSMRecord(Base):
    """Half-finished onboarding, kept in the database rather than in process memory.

    Without this a restart drops every in-flight registration and the donor's next tap
    goes unanswered. See app/bot/storage.py.
    """

    __tablename__ = "fsm_state"

    #: bot:chat:user:thread:business:destiny, flattened from aiogram's StorageKey.
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    state: Mapped[str | None] = mapped_column(String(128))
    data: Mapped[dict | None] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AdminCard(Base):
    """The card message we keep editing for one admin on one request."""

    __tablename__ = "admin_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("blood_requests.id"), index=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("admins.telegram_user_id"))
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("request_id", "admin_id", name="uq_admin_card"),)


class EventLog(Base):
    """Append-only transition log backing the success metrics in PRD 9."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    event: Mapped[str] = mapped_column(String(48), index=True)
    donor_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    request_id: Mapped[int | None] = mapped_column(Integer, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON)
