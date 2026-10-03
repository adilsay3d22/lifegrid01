"""Users, roles, site scopes and settings (FR-ADM-01, FR-ADM-02)."""

import uuid
from datetime import datetime
from typing import Any

import pyotp
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import security as sec
from app.core.clock import now
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import Principal, require
from app.core.enums import STAFF_ROLES, Role
from app.core.errors import Problem
from app.modules.admin import service
from app.modules.admin.models import Setting, SettingHistory
from app.modules.audit import service as audit
from app.modules.auth.models import AppUser, RefreshToken, UserSite

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require(Role.admin)
admin_or_auditor = require(Role.admin, Role.auditor)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str | None
    role: Role
    site_ids: list[uuid.UUID]
    active: bool
    totp: bool


def _out(u: AppUser) -> UserOut:
    return UserOut(id=u.id, email=u.email, role=u.role, site_ids=u.site_ids, active=u.active, totp=u.totp_secret_enc is not None)


class UserIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    role: Role
    site_ids: list[uuid.UUID] = []
    password: str = Field(max_length=512)


class UserPatch(BaseModel):
    role: Role | None = None
    site_ids: list[uuid.UUID] | None = None
    active: bool | None = None


class TotpEnrolment(BaseModel):
    otpauth_uri: str


@router.get("/users", response_model=list[UserOut])
def list_users(_: Principal = Depends(admin_or_auditor), db: Session = Depends(get_db)) -> list[UserOut]:
    return [_out(u) for u in db.scalars(select(AppUser).where(AppUser.email.is_not(None)).order_by(AppUser.email))]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserIn, p: Principal = Depends(admin_only), db: Session = Depends(get_db)) -> UserOut:
    if body.role not in STAFF_ROLES:
        raise Problem(422, "invalid_role", "Only staff accounts are created here.")
    if err := sec.password_problem(body.password, service.get(db, "password_min_length")):
        raise Problem(422, err, "Choose a longer, less common password.")
    email = body.email.lower()
    if db.scalar(select(AppUser).where(AppUser.email == email)):
        raise Problem(409, "duplicate_email", "A user with this email exists.")
    u = AppUser(email=email, role=body.role, password_hash=sec.hash_password(body.password),
                sites=[UserSite(site_id=s) for s in body.site_ids])
    db.add(u)
    db.flush()
    audit.record(db, p.user_id, "user.create", "user", u.id, {"role": body.role, "site_ids": body.site_ids})
    db.commit()
    return _out(u)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserPatch, p: Principal = Depends(admin_only), db: Session = Depends(get_db)) -> UserOut:
    u = db.get(AppUser, user_id)
    if not u or u.email is None:
        raise Problem(404, "not_found", "User not found.")
    patch = body.model_dump(exclude_unset=True)
    if "role" in patch:
        if patch["role"] not in STAFF_ROLES:
            raise Problem(422, "invalid_role", "Staff can only hold staff roles.")
        u.role = patch["role"]
    if "site_ids" in patch:
        u.sites = [UserSite(site_id=s) for s in patch["site_ids"]]
    if "active" in patch:
        u.active = patch["active"]
        if not u.active:  # sessions end now: refresh tokens die, access tokens fail the per-request active check
            db.execute(update(RefreshToken).where(RefreshToken.user_id == u.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now()))
    audit.record(db, p.user_id, "user.role_or_scope_change", "user", u.id, patch)
    db.commit()
    return _out(u)


@router.post("/users/{user_id}/totp", response_model=TotpEnrolment)
def enrol_totp(user_id: uuid.UUID, p: Principal = Depends(admin_only), db: Session = Depends(get_db)) -> TotpEnrolment:
    """Issue a new authenticator secret. The URI is shown once; only the encrypted secret is stored."""
    u = db.get(AppUser, user_id)
    if not u or u.email is None:
        raise Problem(404, "not_found", "User not found.")
    secret = sec.new_totp_secret()
    u.totp_secret_enc = sec.encrypt(secret, get_settings().totp_enc_key)
    audit.record(db, p.user_id, "user.totp_enrol", "user", u.id)
    db.commit()
    return TotpEnrolment(otpauth_uri=pyotp.TOTP(secret).provisioning_uri(u.email, issuer_name="LifeGrid"))


class SettingOut(BaseModel):
    key: str
    value: Any
    version: int
    updated_by: uuid.UUID | None
    updated_at: datetime


class SettingChangeOut(BaseModel):
    key: str
    old_value: Any
    new_value: Any
    version: int
    changed_by: uuid.UUID | None
    changed_at: datetime


class SettingsOut(BaseModel):
    settings: list[SettingOut]
    history: list[SettingChangeOut]


class SettingIn(BaseModel):
    value: Any


@router.get("/settings", response_model=SettingsOut)
def list_settings(_: Principal = Depends(admin_or_auditor), db: Session = Depends(get_db)) -> SettingsOut:
    rows = db.scalars(select(Setting).order_by(Setting.key))
    hist = db.scalars(select(SettingHistory).order_by(SettingHistory.id.desc()).limit(100))
    return SettingsOut(settings=[SettingOut.model_validate(r, from_attributes=True) for r in rows],
                       history=[SettingChangeOut.model_validate(h, from_attributes=True) for h in hist])


@router.get("/settings/{key}", response_model=SettingOut)
def get_setting(key: str, _: Principal = Depends(admin_or_auditor), db: Session = Depends(get_db)) -> SettingOut:
    row = db.get(Setting, key)
    if not row:
        raise Problem(404, "unknown_setting", f"No setting named {key}.")
    return SettingOut.model_validate(row, from_attributes=True)


@router.put("/settings/{key}", response_model=SettingOut)
def put_setting(key: str, body: SettingIn, p: Principal = Depends(admin_only), db: Session = Depends(get_db)) -> SettingOut:
    return SettingOut.model_validate(service.put(db, key, body.value, p.user_id), from_attributes=True)
