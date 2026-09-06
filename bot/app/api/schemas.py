"""Wire format for the blood bank integration.

Deliberately narrow: the bot never receives, stores or displays anything about the
patient (PRD 4). A request is a blood group, a quantity, a place and a deadline.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import REAL_GROUPS, RequestStatus


class Hospital(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    address: str = Field(min_length=2, max_length=500)


class RequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The bank's own id for this request. Repeating it makes the POST idempotent.
    external_id: str = Field(min_length=1, max_length=64)
    blood_group: str
    units_needed: int = Field(ge=1, le=50)
    hospital: Hospital
    district: str = Field(min_length=2, max_length=80)
    city: str | None = Field(default=None, max_length=80)
    needed_by: datetime
    #: Set only if the bank assigns appointment slots; otherwise donors are told to
    #: arrive any time before ``needed_by``.
    slot_time: datetime | None = None
    #: Restrict to the identical group instead of the compatibility matrix.
    exact_match: bool = False
    #: Free text shown to donors, e.g. "ask for the day-care counter". Never patient data.
    notes: str | None = Field(default=None, max_length=300)

    @field_validator("blood_group")
    @classmethod
    def _known_group(cls, value: str) -> str:
        allowed = {g.value for g in REAL_GROUPS}
        if value not in allowed:
            raise ValueError(f"blood_group must be one of {sorted(allowed)}")
        return value

    @model_validator(mode="after")
    def _slot_before_deadline(self) -> RequestIn:
        if self.slot_time and self.slot_time > self.needed_by:
            raise ValueError("slot_time cannot be after needed_by")
        return self


class RequestOut(BaseModel):
    public_id: str
    status: RequestStatus
    blood_group: str
    units_needed: int
    confirmed_count: int
    completed_count: int
    deep_link: str
    needed_by: datetime
    #: False when this response replays a request the bank had already created.
    created: bool = True


class CloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: COMPLETED when every unit was collected, CANCELLED when the bank withdrew it.
    status: RequestStatus = RequestStatus.COMPLETED
    reason: str | None = Field(default=None, max_length=200)

    @field_validator("status")
    @classmethod
    def _terminal_only(cls, value: RequestStatus) -> RequestStatus:
        if value == RequestStatus.OPEN:
            raise ValueError("cannot close a request back to OPEN")
        return value


class CompletionIn(BaseModel):
    """One collected donation. Identify the donor by phone or Telegram id."""

    model_config = ConfigDict(extra="forbid")

    phone: str | None = None
    telegram_user_id: int | None = None
    donated_at: date
    #: The group confirmed at the bank; corrects an "I don't know" registration.
    blood_group: str | None = None

    @model_validator(mode="after")
    def _one_identifier(self) -> CompletionIn:
        if not self.phone and not self.telegram_user_id:
            raise ValueError("provide phone or telegram_user_id")
        return self


class CompletionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    donations: list[CompletionIn] = Field(min_length=1, max_length=50)


class CompletionResultOut(BaseModel):
    donor_id: int | None
    recorded: bool
    detail: str


class CompletionsOut(BaseModel):
    public_id: str
    completed_count: int
    results: list[CompletionResultOut]
