"""The compatibility matrix is the one place a bug puts the wrong blood in a patient."""

from __future__ import annotations

import pytest

from app.core.compatibility import CAN_DONATE_TO, can_donate, donor_groups_for
from app.enums import REAL_GROUPS, BloodGroup


def test_o_negative_is_the_universal_donor():
    assert CAN_DONATE_TO[BloodGroup.O_NEG] == frozenset(REAL_GROUPS)


def test_ab_positive_is_the_universal_recipient():
    assert donor_groups_for(BloodGroup.AB_POS) == frozenset(g.value for g in REAL_GROUPS)


def test_ab_positive_donates_only_to_itself():
    assert CAN_DONATE_TO[BloodGroup.AB_POS] == frozenset({BloodGroup.AB_POS})


@pytest.mark.parametrize("group", REAL_GROUPS)
def test_every_group_can_donate_to_itself(group):
    assert can_donate(group, group)


@pytest.mark.parametrize("group", REAL_GROUPS)
def test_a_negative_request_never_draws_positive_donors(group):
    """Rh-positive blood must never reach an Rh-negative recipient."""
    donors = donor_groups_for(BloodGroup.A_NEG)
    assert not any(d.endswith("+") for d in donors)


def test_o_negative_request_accepts_only_o_negative():
    assert donor_groups_for(BloodGroup.O_NEG) == frozenset({BloodGroup.O_NEG.value})


def test_matrix_is_self_consistent():
    """CAN_RECEIVE_FROM must be the exact inverse of CAN_DONATE_TO."""
    for recipient in REAL_GROUPS:
        for donor in donor_groups_for(recipient):
            assert can_donate(donor, recipient)
        for donor in REAL_GROUPS:
            if donor.value not in donor_groups_for(recipient):
                assert not can_donate(donor, recipient)


def test_exact_match_narrows_to_one_group():
    assert donor_groups_for(BloodGroup.AB_POS, exact_match=True) == frozenset({"AB+"})


def test_unknown_group_is_never_compatible():
    assert not can_donate(BloodGroup.UNKNOWN, BloodGroup.AB_POS)
    assert not can_donate(BloodGroup.O_NEG, BloodGroup.UNKNOWN)
    with pytest.raises(ValueError):
        donor_groups_for(BloodGroup.UNKNOWN)
