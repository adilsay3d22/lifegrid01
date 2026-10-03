from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import STAFF, Principal, require
from app.core.enums import Abo, Component, Rh, Role
from app.core.errors import Problem
from app.modules.compatibility import service
from app.modules.compatibility.models import CompatRule

router = APIRouter(tags=["compatibility"])


class DonorGroup(BaseModel):
    donor_abo: Abo
    donor_rh: Rh
    rank: int


class RuleRow(BaseModel):
    recipient_abo: Abo
    recipient_rh: Rh
    donor_abo: Abo
    donor_rh: Rh
    rank: int = Field(ge=1, le=16)


@router.get("/compatibility", response_model=list[DonorGroup])
def compatible(component: Component, abo: Abo, rh: Rh, _: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)) -> list[DonorGroup]:
    return [DonorGroup(donor_abo=a, donor_rh=r, rank=k) for a, r, k in service.donors_for(service.rank_map(db), component, abo, rh)]


@router.get("/admin/compat-rules", response_model=list[RuleRow])
def list_rules(component: Component, _: Principal = Depends(require(Role.admin, Role.auditor)), db: Session = Depends(get_db)) -> list[RuleRow]:
    rows = db.scalars(select(CompatRule).where(CompatRule.component == component))
    return [RuleRow.model_validate(r, from_attributes=True) for r in rows]


@router.put("/admin/compat-rules", response_model=list[RuleRow])
def replace_rules(component: Component, rows: list[RuleRow], p: Principal = Depends(require(Role.admin)), db: Session = Depends(get_db)) -> list[RuleRow]:
    keys = {(r.recipient_abo, r.recipient_rh, r.donor_abo, r.donor_rh) for r in rows}
    if len(keys) != len(rows):
        raise Problem(422, "duplicate_rule", "Each recipient and donor pair may appear once.")
    service.replace(db, component, [(r.recipient_abo, r.recipient_rh, r.donor_abo, r.donor_rh, r.rank) for r in rows], p.user_id)
    return rows
