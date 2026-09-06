"""Eligibility engine (PRD 7.4, P0-4).

Eligibility is *computed, never asked*. A donor qualifies for a request when ALL hold:

1. blood group compatible with the requested group (UNKNOWN is never matched)
2. same district as the request (city only orders waves, it never excludes)
3. age 18-65 on the request date
4. cooldown passed: 90 days since last donation (male), 120 (female) -- NBTC norms
5. not snoozed, not opted out, and not already engaged with this request

The same predicate is expressed twice: once as SQL (to select a wave without loading the
donor table) and once in Python (to check a single donor arriving via a deep link).
``explain_ineligibility`` returns the first failing rule so the bot can say something
useful instead of a flat "no".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from sqlalchemy import ColumnElement, Select, and_, case, exists, or_, select

from app.config import settings
from app.core.compatibility import donor_groups_for
from app.enums import BloodGroup, Sex
from app.models import BloodRequest, Donor, DonorRequest


class Ineligibility(StrEnum):
    NOT_REGISTERED = "NOT_REGISTERED"
    OPTED_OUT = "OPTED_OUT"
    SNOOZED = "SNOOZED"
    UNKNOWN_GROUP = "UNKNOWN_GROUP"
    GROUP_MISMATCH = "GROUP_MISMATCH"
    OTHER_DISTRICT = "OTHER_DISTRICT"
    TOO_YOUNG = "TOO_YOUNG"
    TOO_OLD = "TOO_OLD"
    COOLDOWN = "COOLDOWN"
    ALREADY_ENGAGED = "ALREADY_ENGAGED"


@dataclass(frozen=True)
class AgeWindow:
    """DOB range that satisfies the age rule on ``on_date``."""

    earliest_dob: date  # oldest acceptable donor
    latest_dob: date  # youngest acceptable donor


def age_window(on_date: date) -> AgeWindow:
    return AgeWindow(
        earliest_dob=_shift_years(on_date, -settings.max_age - 1) + timedelta(days=1),
        latest_dob=_shift_years(on_date, -settings.min_age),
    )


def _shift_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 Feb in a non-leap target year
        return d.replace(year=d.year + years, day=28)


def cooldown_days(sex: str | None) -> int:
    """Days that must elapse since the last donation, per NBTC norms."""
    return settings.cooldown_days_female if sex == Sex.FEMALE else settings.cooldown_days_male


def next_eligible_date(last_donation: date, sex: str | None) -> date:
    return last_donation + timedelta(days=cooldown_days(sex))


def age_on(dob: date, on_date: date) -> int:
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


# --------------------------------------------------------------------------------------
# SQL predicate -- used to pick each wave
# --------------------------------------------------------------------------------------


def eligible_donor_condition(request: BloodRequest, today: date) -> ColumnElement[bool]:
    """SQL predicate selecting donors eligible for ``request``."""
    window = age_window(today)
    groups = donor_groups_for(request.blood_group, exact_match=request.exact_match)

    male_cutoff = today - timedelta(days=settings.cooldown_days_male)
    female_cutoff = today - timedelta(days=settings.cooldown_days_female)
    cooldown_cutoff = case(
        (Donor.sex == Sex.FEMALE, female_cutoff),
        else_=male_cutoff,
    )

    already_engaged = exists().where(
        and_(
            DonorRequest.request_id == request.id,
            DonorRequest.donor_id == Donor.telegram_user_id,
        )
    )

    return and_(
        Donor.is_registered.is_(True),
        Donor.opted_out.is_(False),
        or_(Donor.snoozed_until.is_(None), Donor.snoozed_until <= today),
        Donor.blood_group.in_(groups),
        Donor.blood_group != BloodGroup.UNKNOWN,
        Donor.district == request.district,
        Donor.dob.is_not(None),
        Donor.dob.between(window.earliest_dob, window.latest_dob),
        or_(Donor.last_donation_date.is_(None), Donor.last_donation_date <= cooldown_cutoff),
        ~already_engaged,
    )


def eligible_donors_query(request: BloodRequest, today: date, limit: int | None = None) -> Select:
    """Donors for the next wave, ordered per PRD 7.5.

    Same city first, then longest-since-last-donation (never-donated ranks first, since
    an untapped donor has waited longest). Ties break on donor id for a stable order.
    """
    same_city_first = case((Donor.city == request.city, 0), else_=1)
    never_donated_first = case((Donor.last_donation_date.is_(None), 0), else_=1)

    query = (
        select(Donor)
        .where(eligible_donor_condition(request, today))
        .order_by(
            same_city_first,
            never_donated_first,
            Donor.last_donation_date.asc(),
            Donor.telegram_user_id.asc(),
        )
    )
    if limit is not None:
        query = query.limit(limit)
    return query


# --------------------------------------------------------------------------------------
# Python predicate -- used for a single donor (deep link, "open requests" list)
# --------------------------------------------------------------------------------------


def explain_ineligibility(
    donor: Donor,
    request: BloodRequest,
    today: date,
    *,
    engaged: bool = False,
) -> Ineligibility | None:
    """First rule the donor fails, or None when eligible.

    ``engaged`` is passed in by the caller because it needs a database round trip; the
    deep-link handler already has that row loaded.
    """
    if not donor.is_registered:
        return Ineligibility.NOT_REGISTERED
    if donor.opted_out:
        return Ineligibility.OPTED_OUT
    if donor.snoozed_until and donor.snoozed_until > today:
        return Ineligibility.SNOOZED
    if donor.blood_group == BloodGroup.UNKNOWN:
        return Ineligibility.UNKNOWN_GROUP
    if donor.blood_group not in donor_groups_for(
        request.blood_group, exact_match=request.exact_match
    ):
        return Ineligibility.GROUP_MISMATCH
    if donor.district != request.district:
        return Ineligibility.OTHER_DISTRICT
    if donor.dob is None:
        return Ineligibility.NOT_REGISTERED
    age = age_on(donor.dob, today)
    if age < settings.min_age:
        return Ineligibility.TOO_YOUNG
    if age > settings.max_age:
        return Ineligibility.TOO_OLD
    if donor.last_donation_date is not None:
        if next_eligible_date(donor.last_donation_date, donor.sex) > today:
            return Ineligibility.COOLDOWN
    if engaged:
        return Ineligibility.ALREADY_ENGAGED
    return None


def is_eligible(donor: Donor, request: BloodRequest, today: date, *, engaged: bool = False) -> bool:
    return explain_ineligibility(donor, request, today, engaged=engaged) is None
