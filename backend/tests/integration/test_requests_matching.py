"""Phase 6 exit: FR-REQ-01..06, FR-DON-01..07, FR-MAT-01..07, plus low-stock appeals."""

import re
import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import func, select

from app.core import security, sms
from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import Abo, Availability, Rh, Role, UnitStatus
from app.modules.auth.models import AppUser
from app.modules.donors.models import Donor
from app.modules.matching import service as matching
from app.modules.matching.models import DonorMatch
from app.modules.requests.models import BloodRequest
from tests.factories import unit

API = "/api/v1"


def bearer(u: AppUser) -> dict[str, str]:
    tok = security.make_jwt({"sub": str(u.id), "role": u.role.value, "fam": str(uuid.uuid4()), "typ": "access"}, timedelta(minutes=15), now())
    return {"Authorization": f"Bearer {tok}"}


def phone_user(db, role: Role, phone: str) -> AppUser:  # type: ignore[no-untyped-def]
    u = AppUser(role=role, phone_hash=security.phone_hash(phone), phone_enc=security.encrypt(phone, get_settings().phone_enc_key))
    db.add(u)
    db.commit()
    return u


def donor(db, site, i: int = 0, *, abo=Abo.O, rh=Rh.pos, km_off: float = 1.0, **kw):  # type: ignore[no-untyped-def]
    u = phone_user(db, Role.donor, f"+88010000{20000 + i:05d}")
    fields = {"birth_year": 1990, "weight_ok": True, "availability": Availability.available} | kw
    d = Donor(user_id=u.id, abo=abo, rh=rh, area_lat=round(site.lat + km_off / 111, 2), area_lng=round(site.lng, 2),
              consent_version="v1.2", consent_at=now(), **fields)
    db.add(d)
    db.commit()
    return u, d


@pytest.fixture
def requester(db):  # type: ignore[no-untyped-def]
    return phone_user(db, Role.requester, "+8801000009999")


def new_request(client, headers, site_id, **over):  # type: ignore[no-untyped-def]
    body = {"site_id": str(site_id), "abo": "O", "rh": "pos", "component": "red_cells", "units_needed": 2, "urgency": "urgent",
            "needed_by": (now() + timedelta(hours=12)).isoformat()} | over
    return client.post(f"{API}/requests", json=body, headers=headers)


def test_fr_req_01_hospital_and_needed_by_required(client, requester, sites):
    body = {"abo": "O", "rh": "pos", "component": "red_cells", "units_needed": 1, "urgency": "urgent"}
    assert client.post(f"{API}/requests", json=body, headers=bearer(requester)).status_code == 422
    assert new_request(client, bearer(requester), sites["H-MIR"].id).json()["status"] == "submitted"


def test_fr_req_02_unconfirmed_request_never_invites(client, db, requester, sites):
    donor(db, sites["H-MIR"])
    new_request(client, bearer(requester), sites["H-MIR"].id)
    assert db.scalar(select(func.count()).select_from(DonorMatch)) == 0 and not sms.outbox


def test_fr_req_03_stock_covers_so_no_donor_contacted(client, db, auth, requester, sites):
    donor(db, sites["H-MIR"])
    for _ in range(3):
        unit(db, sites["H-MIR"].id)
    rid = new_request(client, bearer(requester), sites["H-MIR"].id).json()["id"]
    r = client.post(f"{API}/requests/{rid}/confirm", headers=auth("lead")).json()
    assert r["status"] == "covered_by_stock" and r["progress"]["donors_notified"] == 0 and r["units_secured"] == 2
    assert len(list(db.scalars(select(DonorMatch)))) == 0


def test_fr_req_02_only_the_sites_lead_confirms(client, auth, requester, sites):
    rid = new_request(client, bearer(requester), sites["H-MIR"].id).json()["id"]
    assert client.post(f"{API}/requests/{rid}/confirm", headers=auth("lead2")).status_code == 403


def test_fr_req_04_matching_only_for_shortfall_and_fr_mat_03_payload(client, db, auth, requester, sites):
    for i in range(6):
        donor(db, sites["H-MIR"], i)
    unit(db, sites["H-MIR"].id)  # 1 of 3 units in stock
    rid = new_request(client, bearer(requester), sites["H-MIR"].id, units_needed=3).json()["id"]
    r = client.post(f"{API}/requests/{rid}/confirm", headers=auth("lead")).json()
    assert r["status"] == "matching" and r["shortfall"] == 2 and r["units_secured"] == 1
    assert 0 < r["progress"]["donors_notified"] <= 6
    texts = [t for _, t in sms.outbox if "near" in t]
    assert texts and all("+880" not in t and "Synthetic" not in t for t in texts)  # group, area, urgency only


def test_fr_req_06_requester_open_limit(client, requester, sites):
    for _ in range(3):
        assert new_request(client, bearer(requester), sites["H-MIR"].id).status_code == 201
    r = new_request(client, bearer(requester), sites["H-MIR"].id)
    assert r.status_code == 429


def test_fr_req_05_requester_sees_progress_others_cannot(client, db, requester, sites):
    rid = new_request(client, bearer(requester), sites["H-MIR"].id).json()["id"]
    assert client.get(f"{API}/requests/{rid}", headers=bearer(requester)).json()["progress"]["donors_notified"] == 0
    other = phone_user(db, Role.requester, "+8801000008888")
    assert client.get(f"{API}/requests/{rid}", headers=bearer(other)).status_code == 404


def test_fr_don_01_registration_needs_consent_and_rounds_area(client, db):
    u = phone_user(db, Role.donor, "+8801000007777")
    body = {"abo": "A", "rh": "neg", "area_lat": 23.81234, "area_lng": 90.36789, "birth_year": 1995, "weight_ok": True}
    assert client.put(f"{API}/donor/profile", json=body, headers=bearer(u)).json()["code"] == "consent_required"
    r = client.put(f"{API}/donor/profile", json={**body, "consent": True}, headers=bearer(u)).json()
    assert (r["area_lat"], r["area_lng"]) == (23.81, 90.37) and r["group_verified"] is False and r["consent_version"] == "v1.2"
    assert client.get(f"{API}/donor/profile", headers=bearer(phone_user(db, Role.donor, "+8801000007778"))).json()["code"] == "not_registered"


def test_fr_mat_01_every_invited_donor_passes_all_filters(client, db, auth, sites):
    h = sites["H-MIR"]
    good = [donor(db, h, i)[1] for i in range(3)]
    bad = [
        donor(db, h, 10, abo=Abo.A)[1],  # incompatible with O+
        donor(db, h, 11, last_donation_on=now().date() - timedelta(days=30))[1],  # FR-DON-02 cooldown
        donor(db, h, 12, availability=Availability.unavailable)[1],
        donor(db, h, 13, km_off=80)[1],  # outside every radius
        donor(db, h, 14, birth_year=1950)[1],  # age
        donor(db, h, 15, weight_ok=False)[1],
    ]
    deferred = donor(db, h, 16)[1]
    client.post(f"{API}/donors/{deferred.id}/deferrals", json={"category": "recent_travel", "eligible_again_on": str(date.today() + timedelta(days=60))},
                headers=auth("coordinator"))  # FR-DON-03
    r = client.post(f"{API}/appeals", json={"site_id": str(h.id), "abo": "O", "rh": "pos", "units": 6, "urgency": "routine"}, headers=auth("manager"))
    assert r.status_code == 201
    for _ in range(3):  # run every wave
        db.query(BloodRequest).update({BloodRequest.next_wave_at: now() - timedelta(minutes=1)})
        db.commit()
        matching.advance(db)
    invited = set(db.scalars(select(DonorMatch.donor_id)))
    assert invited <= {d.id for d in good} and invited
    assert not invited & {d.id for d in [*bad, deferred]}


def test_fr_don_05_quiet_hours_respected_except_emergency_opt_in(client, db, auth, sites, fixed_clock):
    h = sites["H-MIR"]  # fixed clock: 06:00 UTC = 12:00 Dhaka
    quiet_no = donor(db, h, 1, quiet_start=time(11), quiet_end=time(13))[1]
    quiet_yes = donor(db, h, 2, quiet_start=time(11), quiet_end=time(13), emergency_override=True)[1]
    client.post(f"{API}/appeals", json={"site_id": str(h.id), "abo": "O", "rh": "pos", "units": 2, "urgency": "urgent"}, headers=auth("manager"))
    assert not set(db.scalars(select(DonorMatch.donor_id)))
    db.query(BloodRequest).update({BloodRequest.status: "cancelled"})
    db.commit()
    client.post(f"{API}/appeals", json={"site_id": str(h.id), "abo": "O", "rh": "pos", "units": 2, "urgency": "emergency"}, headers=auth("manager"))
    assert set(db.scalars(select(DonorMatch.donor_id))) == {quiet_yes.id} and quiet_no.id


def test_fr_mat_04_accept_opens_thread_phones_hidden_until_both_opt_in(client, db, auth, requester, sites):
    du, _ = donor(db, sites["H-MIR"])
    rid = new_request(client, bearer(requester), sites["H-MIR"].id, units_needed=1).json()["id"]
    client.post(f"{API}/requests/{rid}/confirm", headers=auth("lead"))
    inv = client.get(f"{API}/donor/invitations", headers=bearer(du)).json()[0]
    assert inv["hospital_area"] and "requester" not in str(inv).lower()
    assert client.post(f"{API}/matches/{inv['id']}/respond", json={"accept": True}, headers=bearer(du)).status_code == 204
    match_id = inv["id"]
    assert client.get(f"{API}/requests/{rid}", headers=bearer(requester)).json()["accepted_matches"][0]["id"] == match_id
    client.post(f"{API}/matches/{match_id}/messages", json={"body": "On my way"}, headers=bearer(du))
    t = client.get(f"{API}/matches/{match_id}/messages", headers=bearer(requester)).json()
    assert t["messages"][0]["body"] == "On my way" and t["counterpart_phone"] is None
    client.post(f"{API}/matches/{match_id}/share-phone", headers=bearer(requester))
    assert client.get(f"{API}/matches/{match_id}/messages", headers=bearer(requester)).json()["counterpart_phone"] is None
    client.post(f"{API}/matches/{match_id}/share-phone", headers=bearer(du))
    assert client.get(f"{API}/matches/{match_id}/messages", headers=bearer(requester)).json()["counterpart_phone"] == "+8801000020000"
    stranger = phone_user(db, Role.requester, "+8801000006666")
    assert client.get(f"{API}/matches/{match_id}/messages", headers=bearer(stranger)).status_code == 404


def test_fr_mat_05_no_new_wave_after_coverage(client, db, auth, sites):
    us = [donor(db, sites["H-MIR"], i)[0] for i in range(5)]
    client.post(f"{API}/appeals", json={"site_id": str(sites["H-MIR"].id), "abo": "O", "rh": "pos", "units": 1, "urgency": "urgent"},
                headers=auth("manager"))
    invited_users = [u for u in us if client.get(f"{API}/donor/invitations", headers=bearer(u)).json()]
    for u in invited_users[:2]:  # target = ceil(1 x 1.5) = 2 acceptances
        inv = client.get(f"{API}/donor/invitations", headers=bearer(u)).json()[0]
        client.post(f"{API}/matches/{inv['id']}/respond", json={"accept": True}, headers=bearer(u))
    r = db.scalar(select(BloodRequest))
    if len(invited_users) >= 2:
        assert r.next_wave_at is None
        n = db.scalar(select(func.count()).select_from(DonorMatch))
        db.query(BloodRequest).update({BloodRequest.next_wave_at: now() - timedelta(minutes=1)})
        db.commit()
        matching.advance(db)
        assert db.scalar(select(func.count()).select_from(DonorMatch)) == n


def test_fr_mat_06_escalates_when_no_one_accepts(client, db, auth, sites):
    client.post(f"{API}/appeals", json={"site_id": str(sites["H-MIR"].id), "abo": "O", "rh": "neg", "units": 1, "urgency": "emergency"},
                headers=auth("manager"))  # no donors at all
    for _ in range(4):
        db.query(BloodRequest).update({BloodRequest.next_wave_at: now() - timedelta(minutes=1)})
        db.commit()
        matching.advance(db)
    assert db.scalar(select(BloodRequest)).escalated_at is not None


def test_fr_mat_07_outcome_updates_reliability_and_secures_units(client, db, auth, requester, sites):
    du, d = donor(db, sites["H-MIR"])
    rid = new_request(client, bearer(requester), sites["H-MIR"].id, units_needed=1).json()["id"]
    client.post(f"{API}/requests/{rid}/confirm", headers=auth("lead"))
    inv = client.get(f"{API}/donor/invitations", headers=bearer(du)).json()[0]
    client.post(f"{API}/matches/{inv['id']}/respond", json={"accept": True}, headers=bearer(du))
    db.refresh(d)
    before = float(d.reliability)  # responding alone does not change reliability
    assert client.post(f"{API}/matches/{inv['id']}/outcome", json={"outcome": "donated"}, headers=auth("lead2")).status_code == 403
    assert client.post(f"{API}/matches/{inv['id']}/outcome", json={"outcome": "donated"}, headers=auth("lead")).status_code == 204
    db.refresh(d)
    assert float(d.reliability) != before and d.last_donation_on == now().date()
    assert client.get(f"{API}/requests/{rid}", headers=bearer(requester)).json()["status"] == "fulfilled"
    matches = client.get(f"{API}/requests/{rid}/matches", headers=auth("lead")).json()
    assert matches[0]["status"] == "donated" and "phone" not in str(matches[0])


def test_fr_don_06_delete_keeps_only_anonymous_row(client, db, auth, sites):
    du, d = donor(db, sites["H-MIR"])
    assert client.get(f"{API}/donor/export", headers=bearer(du)).json()["profile"]["ref"] == d.ref
    assert client.delete(f"{API}/donor/profile", headers=bearer(du)).status_code == 204
    db.refresh(d)
    assert d.deleted_at and d.abo is None and d.area_lat is None and d.birth_year is None
    db.refresh(du)
    assert du.phone_enc is None and not du.active
    assert db.scalar(select(func.count()).select_from(Donor)) == 1  # counts stay


def test_fr_don_07_coordinator_verifies_group_without_contact(client, db, auth, sites):
    _, d = donor(db, sites["H-MIR"])
    rows = client.get(f"{API}/donors", headers=auth("coordinator")).json()
    assert rows[0]["ref"] == d.ref and "phone" not in str(rows[0]) and "area_lat" not in rows[0]
    assert client.post(f"{API}/donors/{d.id}/verify-group", headers=auth("coordinator")).status_code == 204
    assert client.get(f"{API}/donors", headers=auth("lead")).status_code == 403  # no public donor directory (SEC-09)


def test_low_stock_appeal_once_per_group(client, db, auth, sites):
    from app.modules.forecasting import service as forecasting
    from tests.integration.test_forecast_plan_api import _history

    _history(db, sites["H-MIR"].id, rate=6)
    forecasting.run(db)
    low = client.get(f"{API}/stock/low", headers=auth("manager")).json()
    row = next(x for x in low if x["site_id"] == str(sites["H-MIR"].id) and (x["abo"], x["rh"]) == ("O", "pos"))
    assert row["available"] == 0 and row["shortfall"] > 0 and row["open_appeal_id"] is None
    body = {"site_id": row["site_id"], "abo": "O", "rh": "pos", "units": row["shortfall"]}
    assert client.post(f"{API}/appeals", json=body, headers=auth("coordinator")).status_code == 201
    assert client.post(f"{API}/appeals", json=body, headers=auth("manager")).json()["code"] == "appeal_open"
    assert client.post(f"{API}/appeals", json=body, headers=auth("lead")).status_code == 403


def test_dev_otp_code_is_returned_only_in_dev(client, db, monkeypatch):
    r = client.post(f"{API}/auth/otp/request", json={"phone": "+8801000005555"}).json()
    assert r["dev_code"] is None  # tests run with ENV=test
    get_settings.cache_clear()
    monkeypatch.setenv("ENV", "dev")
    try:
        r = client.post(f"{API}/auth/otp/request", json={"phone": "+8801000005556"}).json()
        assert re.fullmatch(r"\d{6}", r["dev_code"])
    finally:
        monkeypatch.setenv("ENV", "test")
        get_settings.cache_clear()


def test_cancel_releases_reserved_units(client, db, auth, requester, sites):
    u = unit(db, sites["H-MIR"].id)
    rid = new_request(client, bearer(requester), sites["H-MIR"].id, units_needed=1).json()["id"]
    client.post(f"{API}/requests/{rid}/confirm", headers=auth("lead"))
    db.refresh(u)
    assert u.status is UnitStatus.reserved and str(u.reserved_for) == rid
    assert client.post(f"{API}/requests/{rid}/cancel", headers=bearer(requester)).json()["status"] == "cancelled"
    db.refresh(u)
    assert u.status is UnitStatus.available and u.reserved_for is None
