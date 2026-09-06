"""Eligibility: the guarantee that every ping a donor gets is actionable (PRD goal 3).

The SQL predicate and the Python predicate have to agree, so the wave query and the
deep-link check never disagree about the same donor.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.eligibility import (
    Ineligibility,
    eligible_donors_query,
    explain_ineligibility,
    next_eligible_date,
)
from app.enums import BloodGroup, Sex
from tests.conftest import make_donor, make_request


async def _seed(session, donors, request):
    session.add(request)
    for donor in donors:
        session.add(donor)
    await session.flush()
    return request


async def _wave(session, request, limit=None):
    result = await session.scalars(eligible_donors_query(request, date.today(), limit=limit))
    return [d.telegram_user_id for d in result]


# --------------------------------------------------------------------------------------
# Exclusions
# --------------------------------------------------------------------------------------


async def test_incompatible_group_is_never_notified(session):
    request = make_request(blood_group=BloodGroup.O_NEG)
    donors = [
        make_donor(1, blood_group=BloodGroup.O_NEG),
        make_donor(2, blood_group=BloodGroup.O_POS),
        make_donor(3, blood_group=BloodGroup.AB_POS),
    ]
    await _seed(session, donors, request)
    assert await _wave(session, request) == [1]


async def test_other_district_is_never_notified(session):
    request = make_request(district="Ernakulam")
    donors = [
        make_donor(1, district="Ernakulam"),
        make_donor(2, district="Thrissur", city="Thrissur"),
    ]
    await _seed(session, donors, request)
    assert await _wave(session, request) == [1]


async def test_cooldown_excludes_recent_donors(session):
    request = make_request()
    donors = [
        make_donor(1, last_donation=date.today() - timedelta(days=200)),
        make_donor(2, last_donation=date.today() - timedelta(days=30)),
    ]
    await _seed(session, donors, request)
    assert await _wave(session, request) == [1]


async def test_female_cooldown_is_longer_than_male(session):
    """A 100-day gap clears the male rule (90) but not the female rule (120)."""
    request = make_request()
    hundred_days = date.today() - timedelta(days=100)
    donors = [
        make_donor(1, sex=Sex.MALE, last_donation=hundred_days),
        make_donor(2, sex=Sex.FEMALE, last_donation=hundred_days),
    ]
    await _seed(session, donors, request)
    assert await _wave(session, request) == [1]


async def test_snoozed_and_opted_out_are_never_notified(session):
    request = make_request()
    donors = [
        make_donor(1),
        make_donor(2, opted_out=True),
        make_donor(3, snoozed_until=date.today() + timedelta(days=30)),
        make_donor(4, registered=False),
    ]
    await _seed(session, donors, request)
    assert await _wave(session, request) == [1]


async def test_expired_snooze_lets_the_donor_back_in(session):
    request = make_request()
    donors = [make_donor(1, snoozed_until=date.today() - timedelta(days=1))]
    await _seed(session, donors, request)
    assert await _wave(session, request) == [1]


@pytest.mark.parametrize("age", [17, 66])
async def test_age_bounds_exclude(session, age):
    request = make_request()
    await _seed(session, [make_donor(1, age=age)], request)
    assert await _wave(session, request) == []


async def test_unknown_blood_group_is_never_matched(session):
    request = make_request(blood_group=BloodGroup.AB_POS)
    donors = [make_donor(1, blood_group=BloodGroup.UNKNOWN), make_donor(2)]
    await _seed(session, donors, request)
    assert await _wave(session, request) == [2]


# --------------------------------------------------------------------------------------
# Wave ordering (PRD 7.5)
# --------------------------------------------------------------------------------------


async def test_same_city_donors_come_first(session):
    request = make_request(city="Kochi")
    donors = [
        make_donor(1, city="Aluva", last_donation=None),
        make_donor(2, city="Kochi", last_donation=date.today() - timedelta(days=300)),
    ]
    await _seed(session, donors, request)
    assert await _wave(session, request) == [2, 1]


async def test_never_donated_outranks_long_ago_within_a_city(session):
    request = make_request(city="Kochi")
    donors = [
        make_donor(1, city="Kochi", last_donation=date.today() - timedelta(days=400)),
        make_donor(2, city="Kochi", last_donation=None),
        make_donor(3, city="Kochi", last_donation=date.today() - timedelta(days=1000)),
    ]
    await _seed(session, donors, request)
    assert await _wave(session, request) == [2, 3, 1]


async def test_wave_limit_caps_the_batch(session):
    request = make_request()
    await _seed(session, [make_donor(i) for i in range(1, 6)], request)
    assert len(await _wave(session, request, limit=3)) == 3


# --------------------------------------------------------------------------------------
# The Python predicate agrees with the SQL one
# --------------------------------------------------------------------------------------


async def test_explanations_match_the_sql_predicate(session):
    request = make_request(blood_group=BloodGroup.O_NEG, district="Ernakulam")
    cases = {
        1: (make_donor(1, blood_group=BloodGroup.O_NEG), None),
        2: (make_donor(2, blood_group=BloodGroup.A_POS), Ineligibility.GROUP_MISMATCH),
        3: (
            make_donor(3, blood_group=BloodGroup.O_NEG, district="Kollam", city="Kollam"),
            Ineligibility.OTHER_DISTRICT,
        ),
        4: (
            make_donor(4, blood_group=BloodGroup.O_NEG, last_donation=date.today()),
            Ineligibility.COOLDOWN,
        ),
        5: (make_donor(5, blood_group=BloodGroup.UNKNOWN), Ineligibility.UNKNOWN_GROUP),
        6: (make_donor(6, blood_group=BloodGroup.O_NEG, age=70), Ineligibility.TOO_OLD),
    }
    await _seed(session, [d for d, _ in cases.values()], request)

    for donor, expected in cases.values():
        assert explain_ineligibility(donor, request, date.today()) is expected

    eligible = set(await _wave(session, request))
    assert eligible == {uid for uid, (_, reason) in cases.items() if reason is None}


async def test_already_engaged_is_reported_separately():
    donor = make_donor(1)
    request = make_request()
    assert explain_ineligibility(donor, request, date.today(), engaged=True) is (
        Ineligibility.ALREADY_ENGAGED
    )


def test_next_eligible_date_uses_the_donor_sex():
    donated = date(2026, 1, 1)
    assert next_eligible_date(donated, Sex.MALE) == donated + timedelta(days=90)
    assert next_eligible_date(donated, Sex.FEMALE) == donated + timedelta(days=120)
