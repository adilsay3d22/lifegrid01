"""Phase 4/5 exit over the API: FR-FC-01/02/04, FR-RD-01..05 and 07."""

import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.core.clock import now
from app.core.enums import Abo, Component, Rh, UnitStatus
from app.modules.forecasting import service as forecasting
from app.modules.forecasting.models import Forecast, UsageDaily
from app.modules.inventory.models import BloodUnit, Transfer
from app.modules.redistribution.models import TransferRecommendation
from tests.factories import unit

API = "/api/v1"


def _history(db, site_id, days=120, rate=5):  # type: ignore[no-untyped-def]
    import numpy as np

    rng = np.random.default_rng(0)
    today = now().date()
    for d in range(days, 0, -1):
        db.add(UsageDaily(site_id=site_id, day=today - timedelta(days=d), component=Component.red_cells, abo=Abo.O, rh=Rh.pos,
                          units_used=int(rng.poisson(rate))))
    db.commit()


def test_fr_fc_01_usage_equals_units_issued(client, auth, db, sites, fixed_clock):
    reserved = [unit(db, sites["H-MIR"].id, status=UnitStatus.reserved) for _ in range(3)]
    for u in reserved[:2]:
        assert client.post(f"{API}/units/{u.id}/transition", json={"action": "issue"}, headers=auth("lead")).status_code == 200
    forecasting.aggregate_usage(db, now().astimezone(ZoneInfo("Asia/Dhaka")).date())
    assert db.scalar(select(func.sum(UsageDaily.units_used)).where(UsageDaily.site_id == sites["H-MIR"].id)) == 2


def test_fr_fc_02_nightly_job_writes_7_rows_per_series(client, auth, db, sites):
    _history(db, sites["H-MIR"].id)
    run_id = forecasting.run(db)
    rows = list(db.scalars(select(Forecast).where(Forecast.run_id == run_id)))
    assert len(rows) == 7 and all(float(f.low) <= float(f.point) <= float(f.high) for f in rows)
    assert rows[0].model and rows[0].model_version
    r = client.get(f"{API}/forecasts", params={"site_id": str(sites["H-MIR"].id), "component": "red_cells", "abo": "O", "rh": "pos"},
                   headers=auth("lead")).json()
    assert r["model"] == rows[0].model and len([p for p in r["points"] if p["point"] is not None]) == 7
    assert len([p for p in r["points"] if p["actual"] is not None]) == 28
    assert client.get(f"{API}/forecasts", params={"site_id": str(sites["H-DHN"].id), "component": "red_cells", "abo": "O"},
                      headers=auth("lead")).status_code == 403


def test_fr_fc_04_accuracy_reports_mae_and_coverage(client, auth, db, sites, fixed_clock):
    _history(db, sites["H-MIR"].id, days=120)
    fixed_clock.advance(days=-14)
    forecasting.run(db)
    fixed_clock.advance(days=14)
    r = client.get(f"{API}/forecasts/accuracy", params={"site_id": str(sites["H-MIR"].id)}, headers=auth("lead")).json()
    assert r["scored"] > 0 and r["mae"] >= 0 and 0 <= r["coverage"] <= 1


def _plan_fixture(db, sites):  # type: ignore[no-untyped-def]
    """Bank has plenty of O+, H-MIR has forecast demand and no stock -> plan should move bank -> H-MIR."""
    for _ in range(25):
        unit(db, sites["BB-CEN"].id, days_left=30, commit=False)
    db.commit()
    _history(db, sites["H-MIR"].id, rate=6)
    forecasting.run(db)


def test_fr_rd_01_02_07_plan_on_demand(client, auth, db, sites):
    _plan_fixture(db, sites)
    r = client.post(f"{API}/plans", headers=auth("manager"))
    assert r.status_code == 202 and r.json()["plan_id"]
    plan = client.get(f"{API}/plans/{r.json()['plan_id']}", headers=auth("manager")).json()
    assert plan["solver_status"] == "OPTIMAL" and plan["solver_seconds"] is not None and plan["is_fallback"] is False
    assert plan["projected"]["with"]["short"] < plan["projected"]["without"]["short"]
    recs = plan["recommendations"]
    assert recs and all(x["units"] > 0 and x["reason"] and x["expected_benefit"] for x in recs)
    assert any(x["from_site_id"] == str(sites["BB-CEN"].id) and x["to_site_id"] == str(sites["H-MIR"].id) for x in recs)
    assert client.post(f"{API}/plans", headers=auth("lead")).status_code == 403


def test_fr_rd_04_05_approve_edit_dispatch_receive(client, auth, db, sites):
    _plan_fixture(db, sites)
    plan_id = client.post(f"{API}/plans", headers=auth("manager")).json()["plan_id"]
    rec = next(x for x in client.get(f"{API}/plans/{plan_id}", headers=auth("manager")).json()["recommendations"]
               if x["to_site_id"] == str(sites["H-MIR"].id))
    assert not db.scalar(select(Transfer))  # nothing to dispatch before approval (FR-RD-04)
    assert client.post(f"{API}/recommendations/{rec['id']}/decision", json={"approve": True}, headers=auth("lead")).status_code == 403
    ok = client.post(f"{API}/recommendations/{rec['id']}/decision", json={"approve": True, "units": 2}, headers=auth("manager"))
    assert ok.json()["status"] == "approved" and ok.json()["units"] == 2
    assert client.post(f"{API}/recommendations/{rec['id']}/decision", json={"approve": False}, headers=auth("manager")).status_code == 409
    t = client.get(f"{API}/transfers", headers=auth("manager")).json()[0]
    assert t["status"] == "approved" and t["units"] == 2
    assert client.post(f"{API}/transfers/{t['id']}/receive", headers=auth("lead")).json()["code"] == "invalid_transition"

    d = client.post(f"{API}/transfers/{t['id']}/dispatch", headers=auth("manager")).json()
    assert d["status"] == "dispatched" and len(d["unit_codes"]) == 2
    moving = list(db.scalars(select(BloodUnit).where(BloodUnit.unit_code.in_(d["unit_codes"]))))
    assert all(u.status is UnitStatus.in_transit and u.site_id == sites["BB-CEN"].id for u in moving)  # location unchanged

    assert client.post(f"{API}/transfers/{t['id']}/receive", headers=auth("lead2")).status_code == 403
    r = client.post(f"{API}/transfers/{t['id']}/receive", headers=auth("lead")).json()
    assert r["status"] == "received"
    for u in moving:
        db.refresh(u)
        assert u.status is UnitStatus.available and u.site_id == sites["H-MIR"].id  # moved on receipt (FR-RD-05)


def test_reject_creates_no_transfer(client, auth, db, sites):
    _plan_fixture(db, sites)
    plan_id = client.post(f"{API}/plans", headers=auth("manager")).json()["plan_id"]
    rec_id = db.scalar(select(TransferRecommendation.id).where(TransferRecommendation.plan_id == uuid.UUID(plan_id)).limit(1))
    assert client.post(f"{API}/recommendations/{rec_id}/decision", json={"approve": False}, headers=auth("manager")).json()["status"] == "rejected"
    assert db.scalar(select(func.count()).select_from(Transfer)) == 0


def test_new_plan_supersedes_old_proposals(client, auth, db, sites):
    _plan_fixture(db, sites)
    first = client.post(f"{API}/plans", headers=auth("manager")).json()["plan_id"]
    client.post(f"{API}/plans", headers=auth("manager"))
    old = client.get(f"{API}/plans/{first}", headers=auth("manager")).json()
    assert old["status"] == "expired" and all(x["status"] == "superseded" for x in old["recommendations"])
