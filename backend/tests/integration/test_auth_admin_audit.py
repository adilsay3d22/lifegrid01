"""Phase 1 exit: FR-AUTH-01..04, FR-AUD-01/02, FR-ADM-01/02, SEC-03/05."""

import re

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import func, select

from app.core import sms
from app.main import app
from app.modules.audit import service as audit
from app.modules.audit.models import AuditEvent
from tests.conftest import PASSWORD, totp_now

API = "/api/v1"


def login(client, email, password=PASSWORD):  # type: ignore[no-untyped-def]
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def test_fr_auth_01_staff_password_sign_in(client, users):
    r = login(client, "lead@lifegrid.test")
    assert r.status_code == 200 and r.json()["totp_required"] is False
    me = client.get(f"{API}/me", headers={"Authorization": "Bearer " + r.json()["session"]["access_token"]})
    assert me.json()["role"] == "hospital_lead" and len(me.json()["site_ids"]) == 1


def test_fr_auth_01_wrong_password_is_401_and_audited(client, users, db):
    assert login(client, "lead@lifegrid.test", "wrong-password-123").status_code == 401
    assert db.scalar(select(func.count()).where(AuditEvent.action == "auth.sign_in_failed")) == 1


def test_fr_auth_01_admin_without_valid_code_cannot_sign_in(client, users):
    r = login(client, "admin@lifegrid.test")
    assert r.json()["totp_required"] is True and r.json()["session"] is None
    bad = client.post(f"{API}/auth/totp", json={"challenge": r.json()["challenge"], "code": "000000"})
    assert bad.status_code == 401
    ok = client.post(f"{API}/auth/totp", json={"challenge": r.json()["challenge"], "code": totp_now()})
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "admin"


def test_fr_auth_01_admin_without_authenticator_is_refused(client, users, db):
    users["admin"].totp_secret_enc = None
    db.commit()
    assert login(client, "admin@lifegrid.test").json()["code"] == "totp_setup_required"


def _code() -> str:
    return re.search(r"\d{6}", sms.outbox[-1][1]).group()  # type: ignore[union-attr]


def test_fr_auth_02_phone_code_signs_in_and_creates_account(client, db):
    assert client.post(f"{API}/auth/otp/request", json={"phone": "+880 1000 000 111"}).status_code == 202
    r = client.post(f"{API}/auth/otp/verify", json={"phone": "+8801000000111", "code": _code(), "role": "donor"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "donor"
    # code is single use
    assert client.post(f"{API}/auth/otp/verify", json={"phone": "+8801000000111", "code": _code()}).status_code == 401


def test_fr_auth_02_sixth_wrong_code_locks_number_for_15_minutes(client, db, fixed_clock):
    client.post(f"{API}/auth/otp/request", json={"phone": "+8801000000222"})
    good = _code()
    wrong = "111111" if good != "111111" else "222222"
    for _ in range(5):
        assert client.post(f"{API}/auth/otp/verify", json={"phone": "+8801000000222", "code": wrong}).status_code == 401
    assert client.post(f"{API}/auth/otp/verify", json={"phone": "+8801000000222", "code": wrong}).status_code == 429
    assert client.post(f"{API}/auth/otp/verify", json={"phone": "+8801000000222", "code": good}).status_code == 429
    fixed_clock.advance(minutes=16)
    assert client.post(f"{API}/auth/otp/request", json={"phone": "+8801000000222"}).status_code == 202


def test_sec_03_code_expires_after_5_minutes_and_3_requests_per_hour(client, db, fixed_clock):
    client.post(f"{API}/auth/otp/request", json={"phone": "+8801000000333"})
    code = _code()
    fixed_clock.advance(minutes=6)
    assert client.post(f"{API}/auth/otp/verify", json={"phone": "+8801000000333", "code": code}).status_code == 401
    client.post(f"{API}/auth/otp/request", json={"phone": "+8801000000333"})
    client.post(f"{API}/auth/otp/request", json={"phone": "+8801000000333"})
    assert client.post(f"{API}/auth/otp/request", json={"phone": "+8801000000333"}).status_code == 429


def test_fr_auth_03_access_token_lasts_15_minutes(client, users, fixed_clock):
    tok = login(client, "lead@lifegrid.test").json()["session"]["access_token"]
    fixed_clock.advance(minutes=14)
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    fixed_clock.advance(minutes=2)
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_fr_auth_03_reused_refresh_token_revokes_the_session(client, users):
    login(client, "lead@lifegrid.test")
    first = client.cookies.get("lg_refresh")
    r = client.post(f"{API}/auth/refresh")
    assert r.status_code == 200
    second = client.cookies.get("lg_refresh")
    assert second != first
    client.cookies.set("lg_refresh", first, path="/api/v1/auth")
    assert client.post(f"{API}/auth/refresh").json()["code"] == "refresh_reused"
    client.cookies.set("lg_refresh", second, path="/api/v1/auth")
    assert client.post(f"{API}/auth/refresh").status_code == 401  # whole family revoked


def test_fr_auth_04_lead_cannot_read_other_site_stock(client, auth, sites):
    r = client.get(f"{API}/units", params={"site_id": str(sites["H-DHN"].id)}, headers=auth("lead"))
    assert r.status_code == 403 and r.json()["code"] == "out_of_scope"
    assert client.get(f"{API}/units", params={"site_id": str(sites["H-MIR"].id)}, headers=auth("lead")).status_code == 200


PUBLIC = {"/auth/login", "/auth/totp", "/auth/otp/request", "/auth/otp/verify", "/auth/refresh", "/auth/logout",
          "/healthz", "/readyz"}


def test_sec_05_every_endpoint_requires_auth_by_default():
    def guarded(dependant) -> bool:  # type: ignore[no-untyped-def]
        return any(getattr(d.call, "__lifegrid_auth__", False) or guarded(d) for d in dependant.dependencies)

    routes = [r for r in app.state.api_routes if isinstance(r, APIRoute)]
    assert len(routes) > 20
    unguarded = [r.path for r in routes if r.path.removeprefix(API) not in PUBLIC and not guarded(r.dependant)]
    assert unguarded == []


@pytest.mark.parametrize("who,status", [("admin", 200), ("auditor", 200), ("manager", 403), ("lead", 403), ("coordinator", 403)])
def test_audit_log_roles(client, auth, who, status):
    assert client.get(f"{API}/audit", headers=auth(who)).status_code == status


def test_fr_adm_01_disabling_user_ends_sessions(client, auth, users):
    lead = auth("lead")
    r = client.patch(f"{API}/admin/users/{users['lead'].id}", json={"active": False}, headers=auth("admin"))
    assert r.status_code == 200
    assert client.get(f"{API}/me", headers=lead).status_code == 401


def test_fr_adm_01_role_change_is_audited(client, auth, users, db):
    client.patch(f"{API}/admin/users/{users['lead2'].id}", json={"role": "auditor"}, headers=auth("admin"))
    assert db.scalar(select(func.count()).where(AuditEvent.action == "user.role_or_scope_change")) == 1


def test_sec_01_password_policy(client, auth):
    body = {"email": "new@lifegrid.test", "role": "hospital_lead", "site_ids": []}
    assert client.post(f"{API}/admin/users", json={**body, "password": "short"}, headers=auth("admin")).json()["code"] == "password_too_short"
    assert client.post(f"{API}/admin/users", json={**body, "password": "password1234"}, headers=auth("admin")).json()["code"] == "password_too_common"
    assert client.post(f"{API}/admin/users", json={**body, "password": "a-long-unique-pass-9"}, headers=auth("admin")).status_code == 201


def test_fr_adm_02_setting_change_keeps_old_new_user_time(client, auth, users):
    r = client.put(f"{API}/admin/settings/solver_time_limit_s", json={"value": 45}, headers=auth("admin"))
    assert r.status_code == 200 and r.json()["version"] == 2
    hist = client.get(f"{API}/admin/settings", headers=auth("admin")).json()["history"][0]
    assert (hist["old_value"], hist["new_value"], hist["changed_by"]) == (30, 45, str(users["admin"].id))
    assert client.put(f"{API}/admin/settings/solver_time_limit_s", json={"value": "fast"}, headers=auth("admin")).status_code == 422


def test_fr_aud_01_rolled_back_change_leaves_no_event(db):
    audit.record(db, None, "test.action", "thing", "1")
    db.rollback()
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_fr_aud_02_editing_an_event_breaks_verification_at_that_event(client, auth, db):
    for i in range(5):
        audit.record(db, None, "test.action", "thing", i)
    db.commit()
    assert client.get(f"{API}/audit/verify", headers=auth("auditor")).json()["ok"] is True
    target = db.scalars(select(AuditEvent).order_by(AuditEvent.id).offset(2).limit(1)).one()
    target.data = {"tampered": True}
    db.commit()
    r = client.get(f"{API}/audit/verify", headers=auth("auditor")).json()
    assert r["ok"] is False and r["broken_at"] == target.id


def test_health_and_ready(client):
    assert client.get(f"{API}/healthz").json() == {"status": "ok"}
    assert client.get(f"{API}/readyz").status_code == 200
    r = client.get(f"{API}/healthz")
    assert r.headers["x-frame-options"] == "DENY" and "x-request-id" in r.headers


def test_errors_are_problem_details(client):
    r = client.post(f"{API}/auth/login", json={"email": "x"})
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")
    assert {"type", "title", "status", "detail", "code"} <= r.json().keys()
