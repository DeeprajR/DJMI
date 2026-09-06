"""ABO/Rh red-cell compatibility (PRD 7.4).

Requests name the *recipient* group. This module answers the only question the
distribution engine asks: which donor groups may give to that recipient.

Rh-negative donors may give to Rh-positive recipients but not the reverse;
O- is the universal donor, AB+ the universal recipient.
"""

from __future__ import annotations

from app.enums import REAL_GROUPS, BloodGroup

#: donor group -> recipient groups that can safely receive it
CAN_DONATE_TO: dict[BloodGroup, frozenset[BloodGroup]] = {
    BloodGroup.O_NEG: frozenset(REAL_GROUPS),
    BloodGroup.O_POS: frozenset(
        {BloodGroup.O_POS, BloodGroup.A_POS, BloodGroup.B_POS, BloodGroup.AB_POS}
    ),
    BloodGroup.A_NEG: frozenset(
        {BloodGroup.A_NEG, BloodGroup.A_POS, BloodGroup.AB_NEG, BloodGroup.AB_POS}
    ),
    BloodGroup.A_POS: frozenset({BloodGroup.A_POS, BloodGroup.AB_POS}),
    BloodGroup.B_NEG: frozenset(
        {BloodGroup.B_NEG, BloodGroup.B_POS, BloodGroup.AB_NEG, BloodGroup.AB_POS}
    ),
    BloodGroup.B_POS: frozenset({BloodGroup.B_POS, BloodGroup.AB_POS}),
    BloodGroup.AB_NEG: frozenset({BloodGroup.AB_NEG, BloodGroup.AB_POS}),
    BloodGroup.AB_POS: frozenset({BloodGroup.AB_POS}),
}

#: recipient group -> donor groups that may give to them (inverse of the above)
CAN_RECEIVE_FROM: dict[BloodGroup, frozenset[BloodGroup]] = {
    recipient: frozenset(d for d, targets in CAN_DONATE_TO.items() if recipient in targets)
    for recipient in REAL_GROUPS
}


def donor_groups_for(recipient: str | BloodGroup, *, exact_match: bool = False) -> frozenset[str]:
    """Donor blood groups eligible for a request needing ``recipient``.

    ``exact_match`` restricts to the identical group -- some banks stock by exact type
    rather than transfusing across the matrix.
    """
    group = BloodGroup(recipient)
    if group is BloodGroup.UNKNOWN:
        raise ValueError("a request cannot ask for an UNKNOWN blood group")
    if exact_match:
        return frozenset({group.value})
    return frozenset(g.value for g in CAN_RECEIVE_FROM[group])


def can_donate(donor: str | BloodGroup, recipient: str | BloodGroup) -> bool:
    """True when a donor of ``donor`` group may give to a ``recipient`` group patient."""
    donor_group = BloodGroup(donor)
    recipient_group = BloodGroup(recipient)
    if BloodGroup.UNKNOWN in (donor_group, recipient_group):
        return False
    return recipient_group in CAN_DONATE_TO[donor_group]
