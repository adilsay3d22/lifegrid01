import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.db import get_db
from app.core.deps import STAFF, Principal, require
from app.core.enums import Abo, Component, MatchStatus, RequestStatus, Rh, Role, Urgency
from app.core.errors import Problem
from app.modules.matching import service as matching
from app.modules.requests import service
from app.modules.requests.models import BloodRequest

router = APIRouter(tags=["requests"])
creators = require(Role.requester, Role.hospital_lead, Role.bank_manager)
readers = require(Role.requester, *STAFF)
appealers = require(Role.bank_manager, Role.donor_coordinator)


class Progress(BaseModel):
    stock_units: int
    donors_notified: int
    donors_accepted: int


class AcceptedMatch(BaseModel):
    id: uuid.UUID
    status: MatchStatus


class RequestOut(BaseModel):
    id: uuid.UUID
    ref: str
    kind: str
    requester_id: uuid.UUID
    site_id: uuid.UUID
    abo: Abo
    rh: Rh
    component: Component
    units_needed: int
    units_secured: int
    urgency: Urgency
    needed_by: datetime
    status: RequestStatus
    confirmed_at: datetime | None
    created_at: datetime
    shortfall: int
    wave: int
    escalated_at: datetime | None
    transfer_plan_id: uuid.UUID | None
    progress: Progress
    accepted_matches: list[AcceptedMatch]


class RequestIn(BaseModel):
    """FR-REQ-01: hospital and needed-by are required (422 without them)."""

    site_id: uuid.UUID
    abo: Abo
    rh: Rh
    component: Component
    units_needed: int = Field(ge=1, le=20)
    urgency: Urgency
    needed_by: AwareDatetime


class UnitsIn(BaseModel):
    units: int = Field(ge=1, le=20)


class MatchOut(BaseModel):
    id: uuid.UUID
    donor_ref: str
    abo: Abo | None
    rh: Rh | None
    group_verified: bool
    wave: int
    score: float
    status: MatchStatus
    invited_at: datetime
    responded_at: datetime | None


class AppealIn(BaseModel):
    site_id: uuid.UUID
    abo: Abo
    rh: Rh
    units: int = Field(ge=1, le=20)
    urgency: Urgency = Urgency.urgent
    hours: int | None = Field(default=None, ge=2, le=336)


class LowStockOut(BaseModel):
    site_id: uuid.UUID
    abo: Abo
    rh: Rh
    available: int
    demand: float
    shortfall: int
    days: int
    open_appeal_id: uuid.UUID | None


@router.get("/requests", response_model=list[RequestOut])
def list_requests(p: Principal = Depends(readers), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(BloodRequest).order_by(BloodRequest.created_at.desc()).limit(200)
    if p.role is Role.requester:
        q = q.where(BloodRequest.requester_id == p.user_id)
    elif not p.region_wide:
        q = q.where(or_(BloodRequest.site_id.in_(p.site_ids), BloodRequest.requester_id == p.user_id))
    return [service.view(db, r, p) for r in db.scalars(q)]


@router.post("/requests", response_model=RequestOut, status_code=201)
def create(body: RequestIn, p: Principal = Depends(creators), db: Session = Depends(get_db)) -> dict[str, Any]:
    ratelimit.hit(f"req:{p.user_id}", 20, 3600)  # SEC-10; the per-day business limit is in the service
    return service.view(db, service.create(db, p, body.model_dump()), p)


@router.get("/requests/{request_id}", response_model=RequestOut)
def get(request_id: uuid.UUID, p: Principal = Depends(readers), db: Session = Depends(get_db)) -> dict[str, Any]:
    r = service.get(db, request_id)
    if not service.can_see(p, r):
        raise Problem(404, "not_found", "Request not found.")
    return service.view(db, r, p)


@router.post("/requests/{request_id}/confirm", response_model=RequestOut)
def confirm(request_id: uuid.UUID, p: Principal = Depends(require(Role.hospital_lead)), db: Session = Depends(get_db)) -> dict[str, Any]:
    return service.view(db, service.confirm(db, request_id, p), p)


@router.post("/requests/{request_id}/cancel", response_model=RequestOut)
def cancel(request_id: uuid.UUID, p: Principal = Depends(creators), db: Session = Depends(get_db)) -> dict[str, Any]:
    return service.view(db, service.cancel(db, request_id, p), p)


@router.post("/requests/{request_id}/outcome", response_model=RequestOut)
def outcome(request_id: uuid.UUID, body: UnitsIn, p: Principal = Depends(require(Role.hospital_lead)), db: Session = Depends(get_db)) -> dict[str, Any]:
    return service.view(db, service.record_units(db, request_id, body.units, p), p)


@router.get("/requests/{request_id}/matches", response_model=list[MatchOut])
def request_matches(request_id: uuid.UUID, p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    r = service.get(db, request_id)
    p.require_site(r.site_id)
    return matching.request_matches(db, r.id)


@router.get("/stock/low", response_model=list[LowStockOut])
def low_stock(_: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return service.low_stock(db)


@router.post("/appeals", response_model=RequestOut, status_code=201)
def create_appeal(body: AppealIn, p: Principal = Depends(appealers), db: Session = Depends(get_db)) -> dict[str, Any]:
    ratelimit.hit(f"appeal:{p.user_id}", 10, 3600)  # SEC-10 invitations
    return service.view(db, service.appeal(db, p, body.site_id, body.abo, body.rh, body.units, body.urgency, body.hours), p)
