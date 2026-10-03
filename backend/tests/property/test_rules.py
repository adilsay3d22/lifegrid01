"""Property tests: compatibility never suggests an incompatible unit (FR-CMP-03); lifecycle never reaches an invalid state."""

from datetime import UTC, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.enums import GROUPS, Component, Role, UnitStatus
from app.modules.compatibility.rules import immunologically_safe, seed_rows
from app.modules.compatibility.service import donors_for
from app.modules.inventory.rules import ALLOWED, SYSTEM, can, pick_fefo

RANKS = {(c, ra, rr, da, dr): k for c, ra, rr, da, dr, k in seed_rows()}


@given(st.sampled_from([Component.red_cells, Component.plasma]), st.sampled_from(GROUPS))
def test_fr_cmp_03_no_incompatible_suggestion(component, recipient):
    for da, dr, _ in donors_for(RANKS, component, *recipient):
        assert immunologically_safe(component, *recipient, da, dr)


def test_fr_cmp_03_every_safe_red_cell_pair_is_offered():
    for r in GROUPS:
        offered = {(a, h) for a, h, _ in donors_for(RANKS, Component.red_cells, *r)}
        assert offered == {d for d in GROUPS if immunologically_safe(Component.red_cells, *r, *d)}


def test_platelets_prefer_identical_group():
    for r in GROUPS:
        assert donors_for(RANKS, Component.platelets, *r)[0][:2] == r


TERMINAL = {UnitStatus.issued, UnitStatus.discarded}


@settings(max_examples=300)
@given(st.lists(st.sampled_from(list(UnitStatus)), max_size=25), st.sampled_from(["system", "hospital_lead", "bank_manager"]))
def test_lifecycle_walk_stays_on_allowed_edges(targets, actor):
    """Apply random requested changes through can(); only allowed edges ever happen; terminal states stay terminal."""
    state: UnitStatus = UnitStatus.available
    for to in targets:
        if can(state, to, actor if actor == SYSTEM else Role(actor)):
            assert (state, to) in ALLOWED
            assert state not in TERMINAL
            state = to


class _U:
    def __init__(self, status: UnitStatus, days: float, t0: datetime) -> None:
        self.status, self.expires_at = status, t0 + timedelta(days=days)


@given(st.lists(st.tuples(st.sampled_from(list(UnitStatus)), st.floats(0, 40)), max_size=30), st.integers(0, 10), st.floats(0, 6))
def test_fr_inv_09_fefo_picks_earliest_eligible(units, n, min_life):
    t0 = datetime(2026, 10, 2, tzinfo=UTC)
    pool = [_U(s, d, t0) for s, d in units]
    picked = pick_fefo(pool, n, timedelta(days=min_life), t0)
    eligible = sorted((u for u in pool if u.status is UnitStatus.available and u.expires_at - t0 >= timedelta(days=min_life)),
                      key=lambda u: u.expires_at)
    assert [u.expires_at for u in picked] == [u.expires_at for u in eligible[:n]]


# ----- FR-MAT-01: matching never invites an ineligible donor ------------------------------------------------------
from datetime import date, time  # noqa: E402

from app.core.enums import Abo, Availability, Rh  # noqa: E402
from app.modules.matching.rules import Candidate, Rules, eligible_from, in_quiet_hours, km, why_not  # noqa: E402

SITE = (23.78, 90.40)
TODAY = date(2026, 10, 2)
maybe = st.one_of(st.none(), st.integers(0, 400))


@settings(max_examples=400)
@given(st.sampled_from(GROUPS), st.sampled_from(list(Availability)), st.integers(1940, 2015), st.booleans(), maybe, maybe,
       st.integers(0, 4), st.integers(0, 4), st.floats(-0.5, 0.5), st.integers(0, 23), st.booleans(), st.booleans(), st.integers(0, 23))
def test_fr_mat_01_eligible_means_every_rule_holds(group, avail, birth, weight, last_days, defer_days, invites, max_inv, off, hour,
                                                   override, emergency, quiet_from):
    c = Candidate("x", *group, False, SITE[0] + off, SITE[1], birth, weight,
                  TODAY - timedelta(days=last_days) if last_days is not None else None,
                  TODAY + timedelta(days=defer_days) if defer_days is not None else None,
                  avail, time(quiet_from), time((quiet_from + 8) % 24), override, max_inv, invites, 0, 0, 0, 0, None)
    compatible = {(Abo.O, Rh.neg), (Abo.O, Rh.pos)}
    needed_by, rules, at = TODAY + timedelta(days=1), Rules(), time(hour)
    if why_not(c, compatible=compatible, site=SITE, radius_km=20, needed_by=needed_by, today=TODAY, local_time=at,
               emergency=emergency, rules=rules) is None:
        assert (c.abo, c.rh) in compatible and c.availability is Availability.available
        nxt = eligible_from(c.last_donation_on, c.deferred_until, rules.cooldown_days)
        assert nxt is None or nxt <= needed_by
        assert 18 <= TODAY.year - birth <= 60 and weight and invites < max_inv
        assert not in_quiet_hours(at, c.quiet_start, c.quiet_end) or (emergency and override)
        assert km((c.lat, c.lng), SITE) <= 20
