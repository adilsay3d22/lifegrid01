"""Donor eligibility, score and invitation waves as pure functions (spec sections 6 and 13.3)."""

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.core.enums import Abo, Availability, Rh


@dataclass
class Candidate:
    id: str
    abo: Abo | None
    rh: Rh | None
    verified: bool
    lat: float | None
    lng: float | None
    birth_year: int | None
    weight_ok: bool | None
    last_donation_on: date | None
    deferred_until: date | None
    availability: Availability
    quiet_start: time | None
    quiet_end: time | None
    emergency_override: bool
    max_invites_30d: int
    invites_30d: int
    invitations: int
    responses: int
    acceptances: int
    donations: int
    last_invited_at: datetime | None
    deleted: bool = False


@dataclass
class Rules:
    cooldown_days: int = 120
    age_min: int = 18
    age_max: int = 60


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def eligible_from(last_donation_on: date | None, deferred_until: date | None, cooldown_days: int) -> date | None:
    """First date the donor may donate again, or None if already eligible from any date."""
    dates = [d for d in (last_donation_on + timedelta(days=cooldown_days) if last_donation_on else None, deferred_until) if d]
    return max(dates) if dates else None


def in_quiet_hours(t: time, start: time | None, end: time | None) -> bool:
    if start is None or end is None or start == end:
        return False
    return start <= t < end if start < end else (t >= start or t < end)  # wraps midnight


def why_not(c: Candidate, *, compatible: set[tuple[Abo, Rh]], site: tuple[float, float], radius_km: float,
            needed_by: date, today: date, local_time: time, emergency: bool, rules: Rules) -> str | None:
    """Reason a donor cannot be invited, or None if eligible (FR-MAT-01). Order: cheapest checks first."""
    if c.deleted:
        return "deleted"
    if c.abo is None or c.rh is None or (c.abo, c.rh) not in compatible:
        return "group"
    if c.availability is not Availability.available:
        return "availability"
    nxt = eligible_from(c.last_donation_on, c.deferred_until, rules.cooldown_days)
    if nxt and nxt > needed_by:
        return "cooldown_or_deferral"
    if c.birth_year is None or not (rules.age_min <= today.year - c.birth_year <= rules.age_max):
        return "age"
    if c.weight_ok is False:
        return "weight"
    if c.invites_30d >= c.max_invites_30d:
        return "invite_limit"
    if in_quiet_hours(local_time, c.quiet_start, c.quiet_end) and not (emergency and c.emergency_override):
        return "quiet_hours"
    if c.lat is None or c.lng is None or km((c.lat, c.lng), site) > radius_km:
        return "distance"
    return None


def reliability(c: Candidate) -> float:
    return ((c.responses + 1) / (c.invitations + 2) + (c.donations + 1) / (c.acceptances + 2)) / 2


def accept_probability(c: Candidate) -> float:
    return (c.acceptances + 1) / (c.invitations + 2)


def score(c: Candidate, *, recipient: tuple[Abo, Rh], site: tuple[float, float], radius_km: float, at: datetime,
          weights: dict[str, float]) -> float:
    """0.40 P + 0.20 G + 0.25 R + 0.15 F (spec 13.3). Exact group = 1, compatible substitute = 0.5."""
    p = 1 - min(km((c.lat or 0, c.lng or 0), site) / radius_km, 1)
    g = 1.0 if (c.abo, c.rh) == recipient else 0.5
    f = 1.0 if c.last_invited_at is None else min((at - c.last_invited_at) / timedelta(days=30), 1.0)
    return round(weights["proximity"] * p + weights["group_fit"] * g + weights["reliability"] * reliability(c) + weights["fairness"] * f, 4)


def wave(scored: list[tuple[Candidate, float]], shortfall: int, seed: str, margin: float = 0.5) -> list[tuple[Candidate, float]]:
    """Invite in score order until expected acceptances reach shortfall x (1 + margin). Ties: verified group first,
    then a seeded random order (deterministic per request)."""
    rnd = random.Random(seed)
    order = list(scored)
    rnd.shuffle(order)
    order.sort(key=lambda cs: (-cs[1], not cs[0].verified))
    out: list[tuple[Candidate, float]] = []
    expected = 0.0
    for c, s in order:
        if expected >= shortfall * (1 + margin):
            break
        out.append((c, s))
        expected += accept_probability(c)
    return out
