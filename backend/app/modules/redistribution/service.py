"""Transfer plans, approval, dispatch and receipt (FR-RD-01..07). The optimizer itself is pure (optimizer.py)."""

import math
import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.deps import Principal
from app.core.enums import Abo, Component, Rh, Role, SiteType
from app.core.enums import UnitStatus as S
from app.core.errors import Problem
from app.modules.admin import service as settings
from app.modules.audit import service as audit
from app.modules.compatibility import service as compat
from app.modules.forecasting.models import Forecast
from app.modules.inventory import service as inventory
from app.modules.inventory.models import BloodUnit, Transfer, UnitMovement
from app.modules.inventory.rules import pick_fefo
from app.modules.redistribution.models import TransferPlan, TransferRecommendation
from app.modules.redistribution.optimizer import Evaluation, Move, PlanInput, bucket, optimize
from app.modules.sites.models import Site


def _haversine(a: Site, b: Site) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a.lat, a.lng, b.lat, b.lng))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(h)), 2)


def build_input(db: Session, c: Component, sites: list[Site], ranks: compat.RankMap) -> PlanInput:
    H = int(settings.get(db, "plan_horizon_days"))
    min_life = int(settings.get(db, "min_transfer_life_days")[c.value])
    k = float(settings.get(db, "optimizer_demand_k"))
    t = now()
    ids = [str(s.id) for s in sites]
    stock: dict[tuple[str, Abo, Rh, int], int] = defaultdict(int)
    for site_id, a, r, exp in db.execute(select(BloodUnit.site_id, BloodUnit.abo, BloodUnit.rh, BloodUnit.expires_at)
                                         .where(BloodUnit.status == S.available, BloodUnit.component == c, BloodUnit.expires_at > t)):
        stock[(str(site_id), a, r, bucket(int((exp - t) / timedelta(days=1)), H, min_life))] += 1
    # Demand D = point + k (high - point) from each site's latest forecast run (spec 13.2).
    demand: dict[tuple[str, Abo, Rh, int], float] = {}
    today = t.date()
    for s in sites:
        run_id = db.scalar(select(Forecast.run_id).where(Forecast.site_id == s.id, Forecast.component == c)
                           .order_by(Forecast.created_at.desc(), Forecast.id.desc()).limit(1))
        if run_id is None:
            continue
        for f in db.scalars(select(Forecast).where(Forecast.run_id == run_id, Forecast.site_id == s.id, Forecast.component == c,
                                                   Forecast.day >= today, Forecast.day < today + timedelta(days=H))):
            demand[(str(s.id), f.abo, f.rh, (f.day - today).days)] = float(f.point) + k * (float(f.high) - float(f.point))
    w = settings.get(db, "optimizer_weights")
    return PlanInput(sites=ids, dist_km={(str(a.id), str(b.id)): _haversine(a, b) for a in sites for b in sites}, stock=dict(stock),
                     demand=demand, ranks={(ra, rr, da, dr): v for (cc, ra, rr, da, dr), v in ranks.items() if cc is c},
                     horizon=H, min_life_days=min_life, weights=w, lane_capacity=int(settings.get(db, "lane_capacity_units")),
                     max_lanes=int(settings.get(db, "max_outgoing_lanes")))


def _recommendations(inp: PlanInput, moves: list[Move], without: Evaluation) -> list[dict[str, object]]:
    """Aggregate moves per lane and group; attribute benefit: shortage first (destination short of a group this unit
    can serve), the rest as expiry avoided at the source."""
    lines: dict[tuple[str, str, Abo, Rh], int] = defaultdict(int)
    for m in moves:
        lines[(m.from_site, m.to_site, m.abo, m.rh)] += m.units
    short_left = dict(without.short_by)
    expiring_left = dict(without.expired_by)
    out = []
    for (i, j, a, r), n in sorted(lines.items(), key=lambda kv: -kv[1]):
        short = 0
        for (site, ha, hr), v in short_left.items():
            if site == j and (ha, hr, a, r) in inp.ranks and v > 0:
                take = min(n - short, int(round(v)))
                short += take
                short_left[(site, ha, hr)] = v - take
        exp = min(n - short, int(round(expiring_left.get((i, a, r), 0))))
        expiring_left[(i, a, r)] = expiring_left.get((i, a, r), 0) - exp
        out.append({"from": i, "to": j, "abo": a, "rh": r, "units": n,
                    "reason": "projected_shortage" if short > 0 else "expiry_risk" if exp > 0 else "rebalance",
                    "benefit": {"shortage_avoided": short, "expired_avoided": exp, "km": inp.dist_km[(i, j)]}})
    return out


def run_plan(db: Session, actor: uuid.UUID | None = None) -> TransferPlan:
    """Nightly (02:00) or on demand. Supersedes earlier proposals (FR-RD-01)."""
    sites = list(db.scalars(select(Site).where(Site.active).order_by(Site.code)))
    ranks = compat.rank_map(db)
    limit = float(settings.get(db, "solver_time_limit_s"))
    H = int(settings.get(db, "plan_horizon_days"))
    recs: list[tuple[Component, dict[str, object]]] = []
    seconds, fallback, statuses = 0.0, False, set()
    totals = {"without": {"expired": 0.0, "short": 0.0}, "with": {"expired": 0.0, "short": 0.0}}
    by_component: dict[str, dict[str, dict[str, float]]] = {}
    for c in Component:
        inp = build_input(db, c, sites, ranks)
        out = optimize(inp, time_limit_s=limit)
        seconds += out.seconds
        fallback |= out.is_fallback
        statuses.add(out.status)
        for key, ev in (("without", out.without), ("with", out.with_plan)):
            totals[key]["expired"] += ev.expired
            totals[key]["short"] += ev.short
        by_component[c.value] = {"without": {"expired": out.without.expired, "short": out.without.short},
                                 "with": {"expired": out.with_plan.expired, "short": out.with_plan.short}}
        recs += [(c, r) for r in _recommendations(inp, out.moves, out.without)]
    proj: dict[str, Any] = {k: {m: round(v, 1) for m, v in t.items()} for k, t in totals.items()} | {"by_component": by_component}
    # Supersede older proposals; their undecided lines can no longer be approved.
    old = list(db.scalars(select(TransferPlan.id).where(TransferPlan.status == "proposed")))
    if old:
        db.execute(update(TransferPlan).where(TransferPlan.id.in_(old)).values(status="expired"))
        db.execute(update(TransferRecommendation).where(TransferRecommendation.plan_id.in_(old), TransferRecommendation.status == "proposed")
                   .values(status="superseded"))
    plan = TransferPlan(horizon_days=H, status="proposed", solver_status="FALLBACK" if fallback else "OPTIMAL",
                        solver_seconds=round(seconds, 2), is_fallback=fallback, projected=proj)
    db.add(plan)
    db.flush()
    for c, r in recs:
        db.add(TransferRecommendation(plan_id=plan.id, from_site_id=uuid.UUID(str(r["from"])), to_site_id=uuid.UUID(str(r["to"])),
                                      component=c, abo=r["abo"], rh=r["rh"], units=r["units"], reason=r["reason"],
                                      expected_benefit=r["benefit"], status="proposed"))
    audit.record(db, actor, "plan.create", "transfer_plan", plan.id, {"recommendations": len(recs), "fallback": fallback,
                                                                      "solver_seconds": round(seconds, 2)})
    db.commit()
    return plan


def decide(db: Session, rec_id: uuid.UUID, approve: bool, units: int | None, p: Principal) -> TransferRecommendation:
    """Bank manager approves (optionally fewer units) or rejects (FR-RD-04)."""
    rec = db.scalars(select(TransferRecommendation).where(TransferRecommendation.id == rec_id).with_for_update()).first()
    if not rec:
        raise Problem(404, "not_found", "Recommendation not found.")
    if rec.status != "proposed":
        raise Problem(409, "already_decided", f"This recommendation is {rec.status}.")
    if units is not None and not (1 <= units <= rec.units):
        raise Problem(422, "invalid_units", f"Units must be between 1 and {rec.units}.")
    rec.status, rec.decided_by, rec.decided_at = ("approved" if approve else "rejected"), p.user_id, now()
    data: dict[str, object] = {"approve": approve, "proposed_units": rec.units}
    if approve:
        if units is not None and units != rec.units:
            data["approved_units"] = units
            rec.units = units
        db.add(Transfer(recommendation_id=rec.id, from_site_id=rec.from_site_id, to_site_id=rec.to_site_id, component=rec.component,
                        abo=rec.abo, rh=rec.rh, units=rec.units, status="approved"))
    audit.record(db, p.user_id, "transfer.decision", "transfer_recommendation", rec.id, data)
    db.commit()
    return rec


def _can_act_at(p: Principal, site: Site) -> None:
    # Hospital leads act at their own sites; bank managers act for blood banks (decision 0002).
    if p.role is Role.bank_manager and site.type is SiteType.blood_bank:
        return
    if p.role is Role.hospital_lead and site.id in p.site_ids:
        return
    if p.role is Role.bank_manager:
        return  # dispatch from any site in the region (spec endpoint table)
    raise Problem(403, "out_of_scope", "You cannot act for this site.")


def pick(db: Session, t: Transfer) -> list[BloodUnit]:
    min_life = timedelta(days=int(settings.get(db, "min_transfer_life_days")[t.component.value]))
    pool = list(db.scalars(select(BloodUnit).where(BloodUnit.site_id == t.from_site_id, BloodUnit.status == S.available,
                                                   BloodUnit.component == t.component, BloodUnit.abo == t.abo, BloodUnit.rh == t.rh)))
    return pick_fefo(pool, t.units, min_life, now())


def dispatch(db: Session, transfer_id: uuid.UUID, p: Principal) -> Transfer:
    """Pick by FEFO and mark in transit; location does not change yet (FR-RD-05)."""
    t = db.scalars(select(Transfer).where(Transfer.id == transfer_id).with_for_update()).first()
    if not t:
        raise Problem(404, "not_found", "Transfer not found.")
    _can_act_at(p, db.get(Site, t.from_site_id))  # type: ignore[arg-type]
    if t.status != "approved":
        raise Problem(409, "invalid_transition", "Only approved transfers can be dispatched.")  # an unapproved line has no transfer
    picked = pick(db, t)
    if not picked:
        raise Problem(409, "no_eligible_units", "No units at the source meet the minimum remaining shelf life.")
    units = inventory.lock_units(db, [u.id for u in picked])
    inventory.apply_transition(db, units, S.in_transit, "Transfer dispatched", p, transfer_id=t.id, check_scope=False)
    t.status, t.dispatched_at, t.units = "dispatched", now(), len(units)
    audit.record(db, p.user_id, "transfer.dispatch", "transfer", t.id, {"units": len(units)})
    db.commit()
    return t


def receive(db: Session, transfer_id: uuid.UUID, p: Principal) -> Transfer:
    t = db.scalars(select(Transfer).where(Transfer.id == transfer_id).with_for_update()).first()
    if not t:
        raise Problem(404, "not_found", "Transfer not found.")
    dest = db.get(Site, t.to_site_id)
    if not ((p.role is Role.hospital_lead and t.to_site_id in p.site_ids) or (p.role is Role.bank_manager and dest and dest.type is SiteType.blood_bank)):
        raise Problem(403, "out_of_scope", "Only the receiving site can confirm receipt.")
    if t.status != "dispatched":
        raise Problem(409, "invalid_transition", "Only dispatched transfers can be received.")
    ids = list(db.scalars(select(UnitMovement.unit_id).where(UnitMovement.transfer_id == t.id, UnitMovement.to_status == S.in_transit)))
    units = [u for u in inventory.lock_units(db, ids) if u.status is S.in_transit]  # quarantined in transit stay put
    inventory.apply_transition(db, units, S.available, "Received at destination", p, transfer_id=t.id, to_site=t.to_site_id,
                               check_scope=False)
    t.status, t.received_at = "received", now()
    audit.record(db, p.user_id, "transfer.receive", "transfer", t.id, {"units": len(units)})
    db.commit()
    return t
