"""Sign-in, one-time codes and token rotation (FR-AUTH-01..03, SEC-01..04)."""

import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import security as sec
from app.core import sms
from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import STAFF_ROLES, Role
from app.core.errors import Problem
from app.modules.admin import service as settings_svc
from app.modules.audit import service as audit
from app.modules.auth.models import AppUser, OtpChallenge, RefreshToken
from app.modules.auth.schemas import LoginOut, Me, TokenOut


def me(u: AppUser) -> Me:
    return Me(id=u.id, role=u.role, email=u.email, site_ids=u.site_ids)


def _issue(db: Session, u: AppUser, family: uuid.UUID | None = None) -> tuple[TokenOut, str]:
    s, t = get_settings(), now()
    fam = family or uuid.uuid4()
    raw = sec.new_refresh_token()
    db.add(RefreshToken(user_id=u.id, family_id=fam, token_hash=sec.token_hash(raw), expires_at=t + timedelta(days=s.refresh_ttl_days)))
    access = sec.make_jwt({"sub": str(u.id), "role": u.role.value, "fam": str(fam), "typ": "access"},
                          timedelta(minutes=s.access_ttl_minutes), t)
    return TokenOut(access_token=access, expires_in=s.access_ttl_minutes * 60, user=me(u)), raw


def login(db: Session, email: str, password: str) -> tuple[LoginOut, str | None]:
    u = db.scalar(select(AppUser).where(AppUser.email == email.strip().lower()))
    if not u or u.role not in STAFF_ROLES or not sec.verify_password(u.password_hash, password):
        audit.record(db, u.id if u else None, "auth.sign_in_failed", "user", u.id if u else "unknown", {"reason": "credentials"})
        db.commit()
        raise Problem(401, "invalid_credentials", "Email or password is incorrect.")
    if not u.active:
        raise Problem(403, "user_disabled", "This account is disabled.")
    if u.role == Role.admin and not u.totp_secret_enc:
        raise Problem(403, "totp_setup_required", "Administrators must set up an authenticator before signing in.")
    if u.totp_secret_enc:
        challenge = sec.make_jwt({"sub": str(u.id), "typ": "totp"}, timedelta(minutes=5), now())
        return LoginOut(totp_required=True, challenge=challenge), None
    out, raw = _issue(db, u)
    audit.record(db, u.id, "auth.sign_in", "user", u.id, {"method": "password"})
    db.commit()
    return LoginOut(totp_required=False, session=out), raw


def verify_totp(db: Session, challenge: str, code: str) -> tuple[TokenOut, str]:
    claims = sec.read_jwt(challenge, "totp")
    u = db.get(AppUser, uuid.UUID(claims["sub"])) if claims else None
    if not u or not u.active or not u.totp_secret_enc:
        raise Problem(401, "invalid_challenge", "Sign in again.")
    secret = sec.decrypt(u.totp_secret_enc, get_settings().totp_enc_key)
    if not sec.verify_totp(secret, code, now()):
        audit.record(db, u.id, "auth.sign_in_failed", "user", u.id, {"reason": "totp"})
        db.commit()
        raise Problem(401, "invalid_code", "That code is not valid.")
    out, raw = _issue(db, u)
    audit.record(db, u.id, "auth.sign_in", "user", u.id, {"method": "password+totp"})
    db.commit()
    return out, raw


def request_otp(db: Session, phone_raw: str) -> str | None:
    phone = sec.normalize_phone(phone_raw)
    if not phone:
        raise Problem(422, "invalid_phone", "Enter a valid phone number with country code.")
    h, t = sec.phone_hash(phone), now()
    last = db.scalar(select(OtpChallenge).where(OtpChallenge.phone_hash == h).order_by(OtpChallenge.created_at.desc()).limit(1))
    if last and last.locked_until and last.locked_until > t:
        raise Problem(429, "locked", "Too many attempts. Try again later.")
    recent = db.scalar(select(func.count()).select_from(OtpChallenge)
                       .where(OtpChallenge.phone_hash == h, OtpChallenge.created_at > t - timedelta(hours=1))) or 0
    if recent >= settings_svc.get(db, "otp_requests_per_hour"):
        raise Problem(429, "rate_limited", "Too many codes requested. Try again in an hour.")
    code = sec.new_otp_code()
    db.add(OtpChallenge(phone_hash=h, code_hash=sec.code_hash(h, code), created_at=t,
                        expires_at=t + timedelta(minutes=settings_svc.get(db, "otp_ttl_minutes"))))
    db.commit()
    sms.send(phone, f"Your LifeGrid code is {code}. It expires in 5 minutes.")
    s = get_settings()
    # Dev and hosted demo only: no real SMS provider, so hand the code to the screen (decisions 0005, 0006). Never in production.
    return code if s.env in ("dev", "demo") and s.sms_provider == "mock" else None


def verify_otp(db: Session, phone_raw: str, code: str, role: str) -> tuple[TokenOut, str]:
    phone = sec.normalize_phone(phone_raw)
    if not phone:
        raise Problem(422, "invalid_phone", "Enter a valid phone number with country code.")
    h, t = sec.phone_hash(phone), now()
    ch = db.scalar(select(OtpChallenge).where(OtpChallenge.phone_hash == h).order_by(OtpChallenge.created_at.desc()).limit(1))
    if ch and ch.locked_until and ch.locked_until > t:
        raise Problem(429, "locked", "Too many attempts. Try again later.")
    if not ch or ch.expires_at <= t:
        raise Problem(401, "invalid_code", "That code is not valid or has expired.")
    if ch.code_hash != sec.code_hash(h, code):
        ch.attempts += 1
        if ch.attempts > settings_svc.get(db, "otp_max_attempts"):  # sixth wrong code locks the number (FR-AUTH-02)
            ch.locked_until = t + timedelta(minutes=settings_svc.get(db, "otp_lock_minutes"))
            db.commit()
            raise Problem(429, "locked", "Too many attempts. This number is locked for 15 minutes.")
        db.commit()
        raise Problem(401, "invalid_code", "That code is not valid.")
    ch.expires_at = t  # single use
    u = db.scalar(select(AppUser).where(AppUser.phone_hash == h))
    if u is None:
        u = AppUser(role=Role(role), phone_hash=h, phone_enc=sec.encrypt(phone, get_settings().phone_enc_key))
        db.add(u)
        db.flush()
        audit.record(db, u.id, "user.create", "user", u.id, {"role": role, "via": "otp"})
    if not u.active:
        raise Problem(403, "user_disabled", "This account is disabled.")
    out, raw = _issue(db, u)
    audit.record(db, u.id, "auth.sign_in", "user", u.id, {"method": "otp"})
    db.commit()
    return out, raw


def refresh(db: Session, raw: str | None) -> tuple[TokenOut, str]:
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sec.token_hash(raw))) if raw else None
    if not row:
        raise Problem(401, "invalid_refresh", "Sign in again.")
    t = now()
    if row.revoked_at is not None:
        # Reuse of a rotated token: assume theft and end the whole session family (FR-AUTH-03).
        _revoke_family(db, row.family_id)
        audit.record(db, row.user_id, "auth.refresh_reuse", "user", row.user_id, {"family": str(row.family_id)})
        db.commit()
        raise Problem(401, "refresh_reused", "Session ended for safety. Sign in again.")
    u = db.get(AppUser, row.user_id)
    if row.expires_at <= t or not u or not u.active:
        raise Problem(401, "invalid_refresh", "Sign in again.")
    row.revoked_at = t
    out, new_raw = _issue(db, u, row.family_id)
    db.commit()
    return out, new_raw


def _revoke_family(db: Session, family: uuid.UUID) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.family_id == family, RefreshToken.revoked_at.is_(None)).values(revoked_at=now()))


def logout(db: Session, raw: str | None) -> None:
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sec.token_hash(raw))) if raw else None
    if row:
        _revoke_family(db, row.family_id)
        db.commit()
