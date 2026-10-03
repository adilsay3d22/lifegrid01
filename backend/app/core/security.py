"""Passwords (SEC-01), tokens (SEC-04), field encryption and phone lookup hashes (SEC-06), TOTP (SEC-02)."""

import base64
import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_ph = PasswordHasher()  # argon2id by default

# Short common-password list; extend from a larger list file if needed.
COMMON_PASSWORDS = {
    "password1234", "123456789012", "qwertyuiopas", "passwordpassword", "letmein12345", "iloveyou1234",
    "administrator", "welcome12345", "1234567890ab", "qwerty123456", "changeme1234", "bangladesh123",
}


def password_problem(pw: str, min_len: int) -> str | None:
    if len(pw) < min_len:
        return "password_too_short"
    if pw.lower() in COMMON_PASSWORDS:
        return "password_too_common"
    return None


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hashed: str | None, pw: str) -> bool:
    if not hashed:
        _ph.hash(pw)  # equalise timing for unknown users
        return False
    try:
        return _ph.verify(hashed, pw)
    except VerificationError:
        return False


def _key(b64: str) -> bytes:
    k = base64.b64decode(b64)
    if len(k) != 32:
        raise ValueError("encryption keys must be 32 bytes (base64)")
    return k


def encrypt(plain: str, key_b64: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_key(key_b64)).encrypt(nonce, plain.encode(), None)


def decrypt(blob: bytes, key_b64: str) -> str:
    return AESGCM(_key(key_b64)).decrypt(blob[:12], blob[12:], None).decode()


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"[\s().-]", "", raw)
    if not re.fullmatch(r"\+?\d{9,15}", digits):
        return None
    return digits if digits.startswith("+") else "+" + digits


def phone_hash(phone: str) -> str:
    return hmac.new(_key(get_settings().phone_hash_key), phone.encode(), hashlib.sha256).hexdigest()


def code_hash(phone_h: str, code: str) -> str:
    return hmac.new(_key(get_settings().phone_hash_key), f"{phone_h}:{code}".encode(), hashlib.sha256).hexdigest()


def new_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def make_jwt(claims: dict[str, Any], ttl: timedelta, now: datetime) -> str:
    body = {**claims, "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp()), "jti": uuid.uuid4().hex}
    return jwt.encode(body, get_settings().jwt_secret, algorithm="HS256")


def read_jwt(token: str, typ: str) -> dict[str, Any] | None:
    from app.core.clock import now  # expiry checked against the app clock, not PyJWT's wall clock

    try:
        body: dict[str, Any] = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"],
                                          options={"verify_exp": False, "verify_iat": False, "require": ["exp", "typ", "sub"]})
    except jwt.PyJWTError:
        return None
    if body.get("typ") != typ or body["exp"] <= now().timestamp():
        return None
    return body


def new_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: str, code: str, at: datetime) -> bool:
    return pyotp.TOTP(secret).verify(code, for_time=at, valid_window=1)
