"""Domain enums. Stored as strings so the schema stays portable across sqlite/postgres."""

from __future__ import annotations

from enum import StrEnum


class BloodGroup(StrEnum):
    O_NEG = "O-"
    O_POS = "O+"
    A_NEG = "A-"
    A_POS = "A+"
    B_NEG = "B-"
    B_POS = "B+"
    AB_NEG = "AB-"
    AB_POS = "AB+"
    UNKNOWN = "UNKNOWN"  # donor hasn't been typed yet; never matched until verified


REAL_GROUPS: tuple[BloodGroup, ...] = tuple(g for g in BloodGroup if g is not BloodGroup.UNKNOWN)


class Sex(StrEnum):
    MALE = "M"
    FEMALE = "F"
    OTHER = "O"


class RequestStatus(StrEnum):
    OPEN = "OPEN"
    FILLED = "FILLED"  # required units confirmed; closed to new confirmations
    COMPLETED = "COMPLETED"  # blood bank reported every unit collected
    CANCELLED = "CANCELLED"  # withdrawn by the blood bank
    EXPIRED = "EXPIRED"  # needed-by passed unfulfilled

    @property
    def is_terminal(self) -> bool:
        return self is not RequestStatus.OPEN


class DonorRequestStatus(StrEnum):
    """Per-donor state machine for one request (PRD 7.2)."""

    NOTIFIED = "NOTIFIED"
    ACCEPTED = "ACCEPTED"
    SCREENING = "SCREENING"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    # exits
    DECLINED = "DECLINED"  # explicit "Not this time"
    ELIMINATED = "ELIMINATED"  # failed the questionnaire gate
    CANCELLED = "CANCELLED"  # donor cancelled after confirming
    NO_SHOW = "NO_SHOW"  # marked by blood bank / admin
    REQUEST_FILLED = "REQUEST_FILLED"  # passed screening but units already met -> waitlist


#: Donor states that occupy or may still occupy a unit.
ACTIVE_DONOR_STATES = (
    DonorRequestStatus.NOTIFIED,
    DonorRequestStatus.ACCEPTED,
    DonorRequestStatus.SCREENING,
    DonorRequestStatus.CONFIRMED,
    DonorRequestStatus.COMPLETED,
)
