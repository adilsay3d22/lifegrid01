"""Unit lifecycle (spec section 6): which status changes are allowed, and who may make them.

SYSTEM is the scheduler / internal callers. Bank managers act as site leads for blood-bank sites (decision 0002).
"""

from datetime import datetime, timedelta
from typing import Protocol

from app.core.enums import Role
from app.core.enums import UnitStatus as S

SYSTEM = "system"
Actor = Role | str

_ANY_LEAD: set[Actor] = {Role.hospital_lead, Role.bank_manager}

ALLOWED: dict[tuple[S | None, S], set[Actor]] = {
    (None, S.available): _ANY_LEAD | {SYSTEM},
    (S.available, S.reserved): set[Actor]({SYSTEM, Role.hospital_lead}),
    (S.reserved, S.available): set[Actor]({SYSTEM}),
    (S.reserved, S.issued): set[Actor]({Role.hospital_lead}),
    (S.available, S.in_transit): _ANY_LEAD,
    (S.in_transit, S.available): _ANY_LEAD | {SYSTEM},
    (S.quarantined, S.available): set[Actor]({Role.bank_manager}),
    (S.quarantined, S.discarded): set[Actor]({Role.bank_manager}),
    (S.expired, S.discarded): _ANY_LEAD,
    **{(s, S.quarantined): _ANY_LEAD | {SYSTEM} for s in (S.available, S.reserved, S.in_transit)},
    **{(s, S.expired): {SYSTEM} for s in (S.available, S.reserved, S.in_transit)},
}

# User-facing actions on POST /units/{id}/transition
ACTIONS: dict[str, S] = {"issue": S.issued, "quarantine": S.quarantined, "clear": S.available, "discard": S.discarded}
DESTRUCTIVE = {"quarantine", "discard"}  # need a reason (spec section 15)


def can(frm: S | None, to: S, actor: Actor) -> bool:
    roles = ALLOWED.get((frm, to))
    return roles is not None and actor in roles


class _Pickable(Protocol):
    status: S
    expires_at: datetime


def pick_fefo[U: _Pickable](units: list[U], n: int, min_life: timedelta, at: datetime) -> list[U]:
    """First-expired, first-out among available units with enough shelf life left (FR-INV-09, FR-RD-03)."""
    ok = [u for u in units if u.status is S.available and u.expires_at - at >= min_life]
    return sorted(ok, key=lambda u: u.expires_at)[:n]
