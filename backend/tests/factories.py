"""Small builders for tests (synthetic data only, SEC-17)."""

import itertools
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Abo, Component, Rh, UnitStatus
from app.modules.inventory.models import BloodUnit, UnitMovement

_seq = itertools.count(1)


def unit(db: Session, site_id: uuid.UUID, *, days_left: float = 20, abo: Abo = Abo.O, rh: Rh = Rh.pos,
         component: Component = Component.red_cells, status: UnitStatus = UnitStatus.available, commit: bool = True) -> BloodUnit:
    t = now()
    u = BloodUnit(unit_code=f"TS26-{next(_seq):07d}", abo=abo, rh=rh, component=component, collected_at=t - timedelta(days=10),
                  expires_at=t + timedelta(days=days_left), site_id=site_id, status=status,
                  reserved_for=uuid.uuid4() if status is UnitStatus.reserved else None)
    db.add(u)
    db.flush()
    db.add(UnitMovement(unit_id=u.id, from_status=None, to_status=UnitStatus.available, to_site_id=site_id, reason="fixture", created_at=t))
    if commit:
        db.commit()
    return u
