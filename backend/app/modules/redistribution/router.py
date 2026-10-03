import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import Principal, require
from app.core.enums import Abo, Component, Rh, Role
from app.core.errors import Problem
from app.modules.inventory.models import BloodUnit, Transfer, UnitMovement
from app.modules.inventory.schemas import UnitOut
from app.modules.redistribution import service
from app.modules.redistribution.models import TransferPlan, TransferRecommendation

router = APIRouter(tags=["redistribution"])
manager = require(Role.bank_manager)
movers = require(Role.bank_manager, Role.hospital_lead)


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    plan_id: uuid.UUID
    from_site_id: uuid.UUID
    to_site_id: uuid.UUID
    component: Component
    abo: Abo
    rh: Rh
    units: int
    reason: str
    expected_benefit: dict[str, Any]
    status: str
    decided_by: uuid.UUID | None
    decided_at: datetime | None


class PlanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    horizon_days: int
    status: str
    solver_status: str
    solver_seconds: float | None
    is_fallback: bool
    projected: dict[str, Any]


class PlanOut(PlanSummary):
    recommendations: list[RecommendationOut]


class DecisionIn(BaseModel):
    approve: bool
    units: int | None = Field(default=None, ge=1)


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    recommendation_id: uuid.UUID | None
    from_site_id: uuid.UUID
    to_site_id: uuid.UUID
    component: Component
    abo: Abo
    rh: Rh
    units: int
    status: str
    created_at: datetime
    dispatched_at: datetime | None
    received_at: datetime | None
    unit_codes: list[str] = []


class PlanQueued(BaseModel):
    queued: bool
    plan_id: uuid.UUID | None


@router.post("/plans", response_model=PlanQueued, status_code=202)
def run_now(p: Principal = Depends(manager)) -> PlanQueued:
    """Queue a plan run on the workers (202). With CELERY_ALWAYS_EAGER (dev, tests) it runs inline."""
    from app.workers.tasks import run_plan

    res = run_plan.delay(str(p.user_id))
    return PlanQueued(queued=True, plan_id=uuid.UUID(res.get()) if res.ready() else None)


@router.get("/plans", response_model=list[PlanSummary])
def list_plans(_: Principal = Depends(movers), db: Session = Depends(get_db)) -> list[TransferPlan]:
    # Request-driven proposals (status "request") are reached from their request, not the nightly plan list.
    return list(db.scalars(select(TransferPlan).where(TransferPlan.status != "request").order_by(TransferPlan.created_at.desc()).limit(30)))


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: uuid.UUID, p: Principal = Depends(movers), db: Session = Depends(get_db)) -> PlanOut:
    plan = db.get(TransferPlan, plan_id)
    if not plan:
        raise Problem(404, "not_found", "Plan not found.")
    q = select(TransferRecommendation).where(TransferRecommendation.plan_id == plan_id).order_by(TransferRecommendation.units.desc())
    if not p.region_wide:  # hospital leads see lines touching their sites (spec section 3)
        q = q.where(or_(TransferRecommendation.from_site_id.in_(p.site_ids), TransferRecommendation.to_site_id.in_(p.site_ids)))
    recs = [RecommendationOut.model_validate(r) for r in db.scalars(q)]
    return PlanOut(**PlanSummary.model_validate(plan).model_dump(), recommendations=recs)


@router.post("/recommendations/{rec_id}/decision", response_model=RecommendationOut)
def decide(rec_id: uuid.UUID, body: DecisionIn, p: Principal = Depends(manager), db: Session = Depends(get_db)) -> RecommendationOut:
    return RecommendationOut.model_validate(service.decide(db, rec_id, body.approve, body.units, p))


def _transfer_out(db: Session, t: Transfer) -> TransferOut:
    codes = list(db.scalars(select(BloodUnit.unit_code).join(UnitMovement, UnitMovement.unit_id == BloodUnit.id)
                            .where(UnitMovement.transfer_id == t.id, UnitMovement.to_status == "in_transit")))
    return TransferOut.model_validate(t).model_copy(update={"unit_codes": codes})


@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(p: Principal = Depends(movers), db: Session = Depends(get_db)) -> list[TransferOut]:
    q = select(Transfer).order_by(Transfer.created_at.desc()).limit(200)
    if not p.region_wide:
        q = q.where(or_(Transfer.from_site_id.in_(p.site_ids), Transfer.to_site_id.in_(p.site_ids)))
    return [_transfer_out(db, t) for t in db.scalars(q)]


@router.get("/transfers/{transfer_id}/pick", response_model=list[UnitOut])
def preview_pick(transfer_id: uuid.UUID, p: Principal = Depends(movers), db: Session = Depends(get_db)) -> list[UnitOut]:
    """The units dispatch would pick right now (FEFO, minimum remaining life)."""
    t = db.get(Transfer, transfer_id)
    if not t:
        raise Problem(404, "not_found", "Transfer not found.")
    p.require_site(t.from_site_id)
    return [UnitOut.model_validate(u) for u in service.pick(db, t)]


@router.post("/transfers/{transfer_id}/dispatch", response_model=TransferOut)
def dispatch(transfer_id: uuid.UUID, p: Principal = Depends(movers), db: Session = Depends(get_db)) -> TransferOut:
    return _transfer_out(db, service.dispatch(db, transfer_id, p))


@router.post("/transfers/{transfer_id}/receive", response_model=TransferOut)
def receive(transfer_id: uuid.UUID, p: Principal = Depends(movers), db: Session = Depends(get_db)) -> TransferOut:
    return _transfer_out(db, service.receive(db, transfer_id, p))
