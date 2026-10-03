"""Test harness: in-memory SQLite per test (or DATABASE_URL=postgresql://... for the full Postgres run), fixed clock."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["COOKIE_SECURE"] = "false"
os.environ["CELERY_ALWAYS_EAGER"] = "true"
os.environ["ENV"] = "test"

import uuid  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import pyotp  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402,F401
from app.bootstrap import seed_reference  # noqa: E402
from app.core import clock, ratelimit, security, sms  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.enums import Role, SiteType  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.auth.models import AppUser, UserSite  # noqa: E402
from app.modules.sites.models import Site  # noqa: E402

T0 = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
PASSWORD = "synthetic-test-pass-42"
TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


class Clock:
    def __init__(self) -> None:
        self.t = T0

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **kw: float) -> None:
        from datetime import timedelta

        self.t += timedelta(**kw)


@pytest.fixture(autouse=True)
def fixed_clock() -> Iterator[Clock]:
    c = Clock()
    clock.set_clock(c)
    ratelimit.reset()
    sms.outbox.clear()
    yield c
    clock.set_clock(None)


@pytest.fixture
def db() -> Iterator[Session]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    seed_reference(s)
    yield s
    s.close()


@pytest.fixture
def sites(db: Session) -> dict[str, Site]:
    rows = [("BB-CEN", SiteType.blood_bank, 23.733, 90.395), ("H-MIR", SiteType.hospital, 23.807, 90.369),
            ("H-DHN", SiteType.hospital, 23.746, 90.374), ("H-SAV", SiteType.hospital, 23.858, 90.267)]
    out = {}
    for code, typ, lat, lng in rows:
        s = Site(code=code, name=f"Synthetic {code}", type=typ, lat=lat, lng=lng)
        db.add(s)
        out[code] = s
    db.commit()
    return out


@pytest.fixture
def users(db: Session, sites: dict[str, Site]) -> dict[str, AppUser]:
    """One staff user per role. Admin has TOTP (required). Leads are scoped to H-MIR."""
    enc = get_settings().totp_enc_key
    spec = {
        "manager": (Role.bank_manager, [sites["BB-CEN"].id], False),
        "lead": (Role.hospital_lead, [sites["H-MIR"].id], False),
        "lead2": (Role.hospital_lead, [sites["H-DHN"].id], False),
        "coordinator": (Role.donor_coordinator, [], False),
        "admin": (Role.admin, [], True),
        "auditor": (Role.auditor, [], False),
    }
    out = {}
    for name, (role, site_ids, totp) in spec.items():
        u = AppUser(email=f"{name}@lifegrid.test", role=role, password_hash=security.hash_password(PASSWORD),
                    totp_secret_enc=security.encrypt(TOTP_SECRET, enc) if totp else None,
                    sites=[UserSite(site_id=s) for s in site_ids])
        db.add(u)
        out[name] = u
    db.commit()
    return out


@pytest.fixture
def client(db: Session) -> TestClient:
    return TestClient(app)


def totp_now() -> str:
    return pyotp.TOTP(TOTP_SECRET).at(clock.now())


@pytest.fixture
def auth(client: TestClient, users: dict[str, AppUser]):  # type: ignore[no-untyped-def]
    """auth('lead') -> headers with a bearer token for that seeded user."""
    cache: dict[str, dict[str, str]] = {}

    def get(name: str) -> dict[str, str]:
        if name not in cache:
            r = client.post("/api/v1/auth/login", json={"email": f"{name}@lifegrid.test", "password": PASSWORD})
            assert r.status_code == 200, r.text
            body = r.json()
            if body["totp_required"]:
                r = client.post("/api/v1/auth/totp", json={"challenge": body["challenge"], "code": totp_now()})
                assert r.status_code == 200, r.text
                token = r.json()["access_token"]
            else:
                token = body["session"]["access_token"]
            cache[name] = {"Authorization": f"Bearer {token}"}
        return cache[name]

    return get


def new_id() -> str:
    return str(uuid.uuid4())
