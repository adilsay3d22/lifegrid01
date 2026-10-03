"""Compatibility lookups from the compat_rule table (FR-CMP-01..03)."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.enums import Abo, Component, Rh
from app.modules.admin import service as settings
from app.modules.audit import service as audit
from app.modules.compatibility.models import CompatRule
from app.modules.compatibility.rules import seed_rows

# (component, recipient_abo, recipient_rh, donor_abo, donor_rh) -> rank; absent means incompatible
RankMap = dict[tuple[Component, Abo, Rh, Abo, Rh], int]


def seed(db: Session) -> None:
    if db.scalar(select(CompatRule).limit(1)) is None:
        db.add_all(CompatRule(component=c, recipient_abo=ra, recipient_rh=rr, donor_abo=da, donor_rh=dr, rank=k)
                   for c, ra, rr, da, dr, k in seed_rows())


def rank_map(db: Session) -> RankMap:
    allow_out = settings.get(db, "platelets_allow_out_of_group")
    out: RankMap = {}
    for r in db.scalars(select(CompatRule)):
        if r.component is Component.platelets and not allow_out and r.donor_abo != r.recipient_abo:
            continue
        out[(r.component, r.recipient_abo, r.recipient_rh, r.donor_abo, r.donor_rh)] = r.rank
    return out


def donors_for(ranks: RankMap, component: Component, abo: Abo, rh: Rh) -> list[tuple[Abo, Rh, int]]:
    """Compatible donor groups, most preferred first (FR-CMP-02)."""
    found = [(da, dr, k) for (c, ra, rr, da, dr), k in ranks.items() if c == component and ra == abo and rr == rh]
    return sorted(found, key=lambda x: x[2])


def replace(db: Session, component: Component, rows: list[tuple[Abo, Rh, Abo, Rh, int]], actor: uuid.UUID) -> None:
    db.execute(delete(CompatRule).where(CompatRule.component == component))
    db.add_all(CompatRule(component=component, recipient_abo=ra, recipient_rh=rr, donor_abo=da, donor_rh=dr, rank=k)
               for ra, rr, da, dr, k in rows)
    audit.record(db, actor, "compat_rules.replace", "compat_rule", component.value, {"rows": len(rows)})
    db.commit()
