"""Phase 2 exit: FR-INV-01..09 (Must + Should built), FR-CMP-01/02, concurrency (NFR-05, Postgres only)."""

import os
import threading
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.clock import now
from app.core.db import SessionLocal
from app.core.enums import Abo, Component, Rh, UnitStatus
from app.core.errors import Problem
from app.modules.compatibility.models import CompatRule
from app.modules.inventory import service
from app.modules.inventory.models import BloodUnit, UnitMovement
from tests.factories import unit

API = "/api/v1"


def _new(site_id, **over):  # type: ignore[no-untyped-def]
    t = now()
    body = {"site_id": str(site_id), "unit_code": "LG26-0090001", "abo": "O", "rh": "neg", "component": "red_cells",
            "collected_at": (t - timedelta(days=1)).isoformat(), "expires_at": (t + timedelta(days=41)).isoformat()}
    return {**body, **over}


def test_fr_inv_01_receive_unit(client, auth, sites):
    r = client.post(f"{API}/units", json=_new(sites["H-MIR"].id), headers=auth("lead"))
    assert r.status_code == 201 and r.json()["status"] == "available"
    assert client.post(f"{API}/units", json=_new(sites["H-MIR"].id), headers=auth("lead")).json()["code"] == "duplicate_code"


@pytest.mark.parametrize("bad", [{"abo": None}, {"expires_at": None}, {"unit_code": ""}])
def test_fr_inv_01_missing_field_is_422(client, auth, sites, bad):
    body = {k: v for k, v in _new(sites["H-MIR"].id, **bad).items() if v is not None}
    assert client.post(f"{API}/units", json=body, headers=auth("lead")).status_code == 422


def test_fr_inv_01_expiry_before_collection_is_422(client, auth, sites):
    t = now()
    body = _new(sites["H-MIR"].id, expires_at=(t - timedelta(days=2)).isoformat())
    assert client.post(f"{API}/units", json=body, headers=auth("lead")).status_code == 422


def test_fr_inv_02_expired_unit_cannot_become_reserved(db, sites):
    u = unit(db, sites["H-MIR"].id, status=UnitStatus.expired)
    with pytest.raises(Problem) as e:
        service.apply_transition(db, [u], UnitStatus.reserved, "test", None)
    assert e.value.status == 409


def test_fr_inv_02_api_returns_409_for_invalid_action(client, auth, db, sites):
    u = unit(db, sites["H-MIR"].id)  # available -> issued is not a lifecycle edge
    r = client.post(f"{API}/units/{u.id}/transition", json={"action": "issue"}, headers=auth("lead"))
    assert r.status_code == 409 and r.json()["code"] == "invalid_transition"


def test_fr_inv_02_role_matters(client, auth, db, sites):
    u = unit(db, sites["H-MIR"].id, status=UnitStatus.quarantined)  # clearing quarantine is bank-manager only
    assert client.post(f"{API}/units/{u.id}/transition", json={"action": "clear"}, headers=auth("lead")).status_code == 403


def test_fr_inv_03_one_movement_per_successful_transition(client, auth, db, sites):
    units = [unit(db, sites["H-MIR"].id) for _ in range(4)]
    before = db.scalar(select(func.count()).select_from(UnitMovement))
    ok = client.post(f"{API}/units/transition", json={"unit_ids": [str(u.id) for u in units[:3]], "action": "quarantine",
                                                      "reason": "Fridge alarm"}, headers=auth("lead"))
    assert ok.json() == {"changed": 3}
    bad = client.post(f"{API}/units/transition", json={"unit_ids": [str(units[0].id), str(units[3].id)], "action": "quarantine",
                                                       "reason": "again"}, headers=auth("lead"))
    assert bad.status_code == 409  # all-or-nothing: units[3] untouched
    assert db.scalar(select(func.count()).select_from(UnitMovement)) - before == 3
    db.refresh(units[3])
    assert units[3].status is UnitStatus.available


def test_destructive_action_needs_reason(client, auth, db, sites):
    u = unit(db, sites["H-MIR"].id)
    assert client.post(f"{API}/units/{u.id}/transition", json={"action": "quarantine"}, headers=auth("lead")).json()["code"] == "reason_required"


def test_fr_inv_04_expiry_job(db, sites, fixed_clock):
    a = unit(db, sites["H-MIR"].id, days_left=0.5)
    b = unit(db, sites["H-MIR"].id, days_left=0.5, status=UnitStatus.reserved)
    c = unit(db, sites["H-MIR"].id, days_left=3)
    fixed_clock.advance(hours=13)
    assert service.expire_overdue(db) == 2
    for x in (a, b, c):
        db.refresh(x)
    assert (a.status, b.status, c.status) == (UnitStatus.expired, UnitStatus.expired, UnitStatus.available)
    assert b.reserved_for is None


def test_fr_inv_05_summary_matches_database_count(client, auth, db, sites):
    for d in (1, 1.5, 4, 10, 30):
        unit(db, sites["H-MIR"].id, days_left=d)
    unit(db, sites["H-MIR"].id, status=UnitStatus.quarantined)
    cells = client.get(f"{API}/stock/summary", params={"component": "red_cells"}, headers=auth("lead2")).json()
    mine = [c for c in cells if c["site_id"] == str(sites["H-MIR"].id)]
    assert (sum(c["band_0_2"] for c in mine), sum(c["band_3_7"] for c in mine), sum(c["band_8"] for c in mine)) == (2, 1, 2)
    available = db.scalar(select(func.count()).where(BloodUnit.status == UnitStatus.available, BloodUnit.site_id == sites["H-MIR"].id))
    assert sum(c["band_0_2"] + c["band_3_7"] + c["band_8"] for c in mine) == available


def test_fr_inv_07_excursion_quarantines_and_excludes_from_stock(client, auth, db, sites):
    units = [unit(db, sites["H-MIR"].id) for _ in range(3)]
    unit(db, sites["H-MIR"].id, component=Component.plasma)
    r = client.post(f"{API}/excursions", json={"site_id": str(sites["H-MIR"].id), "component": "red_cells",
                                               "started_at": now().isoformat(), "max_c": 9.4}, headers=auth("lead"))
    assert r.json()["quarantined"] == 3
    for u in units:
        db.refresh(u)
        assert u.status is UnitStatus.quarantined
    cells = client.get(f"{API}/stock/summary", params={"component": "red_cells"}, headers=auth("lead")).json()
    assert not [c for c in cells if c["site_id"] == str(sites["H-MIR"].id)]


def test_fr_inv_08_import_good_rows_and_report_bad(client, auth, sites):
    csv = ("unit_code,abo,rh,component,collected_at,expires_at\n"
           "LG26-0100001,O,pos,red_cells,2026-09-28T08:00:00Z,2026-11-09T08:00:00Z\n"
           "LG26-0100002,Q,pos,red_cells,2026-09-28T08:00:00Z,2026-11-09T08:00:00Z\n"
           "LG26-0100003,A,neg,plasma,2026-09-28T08:00:00Z,2026-09-01T08:00:00Z\n"
           "LG26-0100001,O,pos,red_cells,2026-09-28T08:00:00Z,2026-11-09T08:00:00Z\n"
           "LG26-0100004,B,neg,platelets,2026-09-30T08:00:00Z,2026-10-05T08:00:00Z\n")
    r = client.post(f"{API}/units/import", data={"site_id": str(sites["H-MIR"].id)}, files={"file": ("u.csv", csv, "text/csv")}, headers=auth("lead"))
    assert r.json() == {"imported": 2, "errors": [{"row": 3, "reason": "invalid_abo"}, {"row": 4, "reason": "expiry_before_collection"},
                                                  {"row": 5, "reason": "duplicate_code"}]}


def test_fr_inv_08_bad_header(client, auth, sites):
    r = client.post(f"{API}/units/import", data={"site_id": str(sites["H-MIR"].id)}, files={"file": ("u.csv", "a,b\n1,2", "text/csv")}, headers=auth("lead"))
    assert r.json()["code"] == "bad_header"


def test_fr_inv_09_list_is_fefo_and_paginated(client, auth, db, sites):
    for d in (30, 2, 15, 7, 1):
        unit(db, sites["H-MIR"].id, days_left=d)
    p1 = client.get(f"{API}/units", params={"site_id": str(sites["H-MIR"].id), "limit": 3}, headers=auth("lead")).json()
    p2 = client.get(f"{API}/units", params={"site_id": str(sites["H-MIR"].id), "limit": 3, "cursor": p1["next_cursor"]}, headers=auth("lead")).json()
    exp = [u["expires_at"] for u in p1["items"] + p2["items"]]
    assert exp == sorted(exp) and len(exp) == 5 and p1["total"] == 5 and p2["next_cursor"] is None


def test_unit_detail_has_timeline(client, auth, db, sites):
    u = unit(db, sites["H-MIR"].id)
    client.post(f"{API}/units/{u.id}/transition", json={"action": "quarantine", "reason": "Dropped bag"}, headers=auth("lead"))
    d = client.get(f"{API}/units/{u.id}", headers=auth("lead")).json()
    assert [m["to_status"] for m in d["movements"]] == ["available", "quarantined"]
    assert client.get(f"{API}/units/{u.id}", headers=auth("lead2")).status_code == 403


def test_fr_cmp_01_changing_a_rule_row_changes_results(client, auth, db):
    def groups():  # type: ignore[no-untyped-def]
        r = client.get(f"{API}/compatibility", params={"component": "red_cells", "abo": "A", "rh": "neg"}, headers=auth("lead"))
        return [(g["donor_abo"], g["donor_rh"]) for g in r.json()]

    assert groups() == [("A", "neg"), ("O", "neg")]
    db.delete(db.get(CompatRule, (Component.red_cells, Abo.A, Rh.neg, Abo.O, Rh.neg)))
    db.commit()
    assert groups() == [("A", "neg")]


def test_fr_cmp_02_exact_first_and_o_negative_last(client, auth):
    for abo, rh in [("AB", "pos"), ("A", "pos"), ("B", "pos"), ("O", "pos")]:
        g = client.get(f"{API}/compatibility", params={"component": "red_cells", "abo": abo, "rh": rh}, headers=auth("lead")).json()
        assert (g[0]["donor_abo"], g[0]["donor_rh"]) == (abo, rh)
        assert (g[-1]["donor_abo"], g[-1]["donor_rh"]) == ("O", "neg")


@pytest.mark.skipif(not os.environ["DATABASE_URL"].startswith("postgresql"), reason="row locks need PostgreSQL")
def test_nfr_05_two_users_dispatching_same_unit_cannot_double_move(db, sites, users):
    from app.core.deps import Principal

    u = unit(db, sites["H-MIR"].id)
    lead = Principal(users["lead"].id, users["lead"].role, None, frozenset([sites["H-MIR"].id]))
    results: list[str] = []

    def worker() -> None:
        s = SessionLocal()
        try:
            service.transition(s, [u.id], UnitStatus.quarantined, "race", lead)
            results.append("ok")
        except Problem as e:
            results.append(e.code)
        finally:
            s.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["invalid_transition", "ok"]
    assert db.scalar(select(func.count()).where(UnitMovement.unit_id == u.id, UnitMovement.to_status == UnitStatus.quarantined)) == 1
