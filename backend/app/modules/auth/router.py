import os

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import Principal, get_principal
from app.modules.auth import service
from app.modules.auth.models import AppUser
from app.modules.auth.schemas import LoginIn, LoginOut, Me, OtpRequestIn, OtpVerifyIn, TokenOut, TotpIn

router = APIRouter(tags=["auth"])
COOKIE = "lg_refresh"


def _set_cookie(resp: Response, raw: str) -> None:
    s = get_settings()
    resp.set_cookie(COOKIE, raw, max_age=s.refresh_ttl_days * 86400, httponly=True, secure=s.cookie_secure,
                    samesite="strict", path="/api/v1/auth")


def _ip(req: Request) -> str:
    if os.environ.get("VERCEL"):  # Vercel overwrites x-real-ip with the caller's address; clients can't spoof it there
        return req.headers.get("x-real-ip", "unknown")
    return req.client.host if req.client else "unknown"


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn, req: Request, resp: Response, db: Session = Depends(get_db)) -> LoginOut:
    ratelimit.hit(f"login:{body.email.lower()}", 10, 900)
    ratelimit.hit(f"login-ip:{_ip(req)}", 50, 900)
    out, raw = service.login(db, body.email, body.password)
    if raw:
        _set_cookie(resp, raw)
    return out


@router.post("/auth/totp", response_model=TokenOut)
def totp(body: TotpIn, req: Request, resp: Response, db: Session = Depends(get_db)) -> TokenOut:
    ratelimit.hit(f"totp-ip:{_ip(req)}", 20, 900)
    out, raw = service.verify_totp(db, body.challenge, body.code)
    _set_cookie(resp, raw)
    return out


class OtpSent(BaseModel):
    sent: bool
    dev_code: str | None = None


@router.post("/auth/otp/request", status_code=202, response_model=OtpSent)
def otp_request(body: OtpRequestIn, req: Request, db: Session = Depends(get_db)) -> OtpSent:
    ratelimit.hit(f"otp-ip:{_ip(req)}", 20, 3600)
    return OtpSent(sent=True, dev_code=service.request_otp(db, body.phone))


@router.post("/auth/otp/verify", response_model=TokenOut)
def otp_verify(body: OtpVerifyIn, req: Request, resp: Response, db: Session = Depends(get_db)) -> TokenOut:
    ratelimit.hit(f"otpv-ip:{_ip(req)}", 30, 900)
    out, raw = service.verify_otp(db, body.phone, body.code, body.role)
    _set_cookie(resp, raw)
    return out


@router.post("/auth/refresh", response_model=TokenOut)
def refresh(req: Request, resp: Response, db: Session = Depends(get_db)) -> TokenOut:
    out, raw = service.refresh(db, req.cookies.get(COOKIE))
    _set_cookie(resp, raw)
    return out


@router.post("/auth/logout", status_code=204)
def logout(req: Request, resp: Response, db: Session = Depends(get_db)) -> Response:
    service.logout(db, req.cookies.get(COOKIE))
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE, path="/api/v1/auth")
    return resp


@router.get("/me", response_model=Me)
def get_me(p: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> Me:
    return service.me(db.get(AppUser, p.user_id))  # type: ignore[arg-type]
