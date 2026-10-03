import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import Principal, get_principal, require
from app.core.enums import Role, SiteType
from app.core.errors import Problem
from app.modules.audit import service as audit
from app.modules.sites.models import Site

router = APIRouter(tags=["sites"])


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    type: SiteType
    lat: float
    lng: float
    timezone: str
    active: bool


class SiteIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9-]{2,16}$")
    name: str = Field(min_length=2, max_length=120)
    type: SiteType
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    timezone: str = "Asia/Dhaka"


class SitePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = None
    active: bool | None = None


@router.get("/sites", response_model=list[SiteOut])
def list_sites(_: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> list[Site]:
    """Any signed-in user: requesters choose a hospital. Names and locations of sites are not personal data."""
    return list(db.scalars(select(Site).order_by(Site.type, Site.code)))


@router.post("/sites", response_model=SiteOut, status_code=201)
def create_site(body: SiteIn, p: Principal = Depends(require(Role.admin)), db: Session = Depends(get_db)) -> Site:
    if db.scalar(select(Site).where(Site.code == body.code)):
        raise Problem(409, "duplicate_code", "A site with this code exists.")
    s = Site(**body.model_dump())
    db.add(s)
    db.flush()
    audit.record(db, p.user_id, "site.create", "site", s.id, body.model_dump())
    db.commit()
    return s


@router.patch("/sites/{site_id}", response_model=SiteOut)
def update_site(site_id: uuid.UUID, body: SitePatch, p: Principal = Depends(require(Role.admin)), db: Session = Depends(get_db)) -> Site:
    s = db.get(Site, site_id)
    if not s:
        raise Problem(404, "not_found", "Site not found.")
    patch = body.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(s, k, v)
    audit.record(db, p.user_id, "site.update", "site", s.id, patch)
    db.commit()
    return s
