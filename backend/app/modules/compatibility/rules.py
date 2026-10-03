"""Seed rows for compat_rule (spec section 6) and the immunological ground truth used by property tests.

At runtime the system reads the compat_rule table, never these constants (FR-CMP-01).
"""

from app.core.enums import GROUPS, Abo, Component, Rh

_RED_CELLS = {
    "O-": ["O-"],
    "O+": ["O+", "O-"],
    "A-": ["A-", "O-"],
    "A+": ["A+", "A-", "O+", "O-"],
    "B-": ["B-", "O-"],
    "B+": ["B+", "B-", "O+", "O-"],
    "AB-": ["AB-", "A-", "B-", "O-"],
    "AB+": ["AB+", "AB-", "A+", "A-", "B+", "B-", "O+", "O-"],
}
_PLASMA = {"O": ["O", "A", "B", "AB"], "A": ["A", "AB"], "B": ["B", "AB"], "AB": ["AB"]}

Row = tuple[Component, Abo, Rh, Abo, Rh, int]


def _parse(g: str) -> tuple[Abo, Rh]:
    return Abo(g[:-1]), Rh.neg if g.endswith("-") else Rh.pos


def seed_rows() -> list[Row]:
    rows: list[Row] = []
    for rec, donors in _RED_CELLS.items():
        ra, rr = _parse(rec)
        for i, d in enumerate(donors):
            da, dr = _parse(d)
            rows.append((Component.red_cells, ra, rr, da, dr, i + 1))
    for ra_s, donors_abo in _PLASMA.items():  # ABO only; both Rh rows kept so lookups stay uniform
        for rr in Rh:
            for dr in Rh:
                for i, da_s in enumerate(donors_abo):
                    rows.append((Component.plasma, Abo(ra_s), rr, Abo(da_s), dr, i + 1))
    for ra, rr in GROUPS:  # platelets: ABO-identical first, then Rh match preferred
        ranked = sorted(GROUPS, key=lambda g: (g[0] != ra) * 2 + (g[1] != rr))
        rows.extend((Component.platelets, ra, rr, da, dr, i + 1) for i, (da, dr) in enumerate(ranked))
    return rows


_ANTIGENS = {Abo.O: set(), Abo.A: {"A"}, Abo.B: {"B"}, Abo.AB: {"A", "B"}}


def immunologically_safe(component: Component, r_abo: Abo, r_rh: Rh, d_abo: Abo, d_rh: Rh) -> bool:
    """Oracle for property tests. Red cells: donor antigens must be a subset of the recipient's.
    Plasma: donor antibodies must not attack recipient cells (donor antigens ⊇ recipient's). Platelets
    allow out-of-group by policy, so only red cells and plasma are checked strictly."""
    if component is Component.red_cells:
        return _ANTIGENS[d_abo] <= _ANTIGENS[r_abo] and (d_rh is Rh.neg or r_rh is Rh.pos)
    if component is Component.plasma:
        return _ANTIGENS[d_abo] >= _ANTIGENS[r_abo]
    return True
