import uuid
from datetime import date, datetime, time
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.db import get_db
from app.core.deps import Principal, require
from app.core.enums import Abo, Availability, Rh, Role
from app.modules.donors import service

router = APIRouter(tags=["donors"])
donor = require(Role.donor)
coordinator = require(Role.donor_coordinator)


class Deferral(BaseModel):
    category: str
    eligible_again_on: date


class DonorOut(BaseModel):
    id: uuid.UUID
    ref: str
    abo: Abo | None
    rh: Rh | None
    group_verified: bool
    area_label: str
    area_lat: float | None
    area_lng: float | None
    birth_year: int | None
    weight_ok: bool | None
    last_donation_on: date | None
    availability: Availability
    reliability: float
    deferral: Deferral | None
    eligible_from: date | None
    quiet_start: time | None
    quiet_end: time | None
    emergency_override: bool
    max_invites_30d: int
    consent_version: str
    consent_at: datetime


class CoordinatorDonorOut(BaseModel):
    """No contact details, no exact location (SEC-08, SEC-09)."""

    id: uuid.UUID
    ref: str
    abo: Abo | None
    rh: Rh | None
    group_verified: bool
    area_label: str
    last_donation_on: date | None
    availability: Availability
    reliability: float
    deferral: Deferral | None
    eligible_from: date | None
    weight_ok: bool | None
    quiet_start: time | None
    quiet_end: time | None
    emergency_override: bool
    max_invites_30d: int
    consent_version: str
    consent_at: datetime


class ProfileIn(BaseModel):
    abo: Abo | None = None
    rh: Rh | None = None
    area_lat: float | None = Field(default=None, ge=-90, le=90)
    area_lng: float | None = Field(default=None, ge=-180, le=180)
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    weight_ok: bool | None = None
    availability: Availability | None = None
    quiet_start: time | None = None
    quiet_end: time | None = None
    emergency_override: bool | None = None
    max_invites_30d: int | None = Field(default=None, ge=0, le=10)
    consent: bool | None = None
    consent_version: str | None = None


class DeferralIn(BaseModel):
    category: str = Field(pattern=r"^[a-z_]{3,40}$")  # category only; never medical detail (SEC-07)
    eligible_again_on: date


@router.get("/donor/profile", response_model=DonorOut)
def get_profile(p: Principal = Depends(donor), db: Session = Depends(get_db)) -> dict[str, Any]:
    return service.view(db, service.mine(db, p.user_id))


@router.put("/donor/profile", response_model=DonorOut)
def put_profile(body: ProfileIn, p: Principal = Depends(donor), db: Session = Depends(get_db)) -> dict[str, Any]:
    return service.view(db, service.upsert(db, p.user_id, body.model_dump(exclude_unset=True)))


@router.get("/donor/export")
def export(p: Principal = Depends(donor), db: Session = Depends(get_db)) -> dict[str, Any]:
    return service.export(db, p.user_id)


@router.delete("/donor/profile", status_code=204)
def delete(p: Principal = Depends(donor), db: Session = Depends(get_db)) -> Response:
    service.delete(db, p.user_id)
    return Response(status_code=204)


@router.get("/donors", response_model=list[CoordinatorDonorOut])
def search(group: str | None = Query(None, pattern=r"^(O|A|B|AB)(pos|neg)$"), eligible: str | None = Query(None, pattern=r"^(yes|no)$"),
           q: str | None = Query(None, max_length=40), p: Principal = Depends(coordinator), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    ratelimit.hit(f"donor-search:{p.user_id}", 120, 60)  # SEC-09
    return [service.view(db, d) for d in service.search(db, group, eligible, q)]


@router.post("/donors/{donor_id}/deferrals", status_code=204)
def defer(donor_id: uuid.UUID, body: DeferralIn, p: Principal = Depends(coordinator), db: Session = Depends(get_db)) -> Response:
    service.add_deferral(db, donor_id, body.category, body.eligible_again_on, p.user_id)
    return Response(status_code=204)


@router.post("/donors/{donor_id}/verify-group", status_code=204)
def verify_group(donor_id: uuid.UUID, p: Principal = Depends(coordinator), db: Session = Depends(get_db)) -> Response:
    service.verify_group(db, donor_id, p.user_id)
    return Response(status_code=204)
