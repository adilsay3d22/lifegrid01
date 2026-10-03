"""Blood requests and low-stock appeals (FR-REQ-01..06). Stock is checked before any donor is contacted."""

import math
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.deps import Principal
from app.core.enums import OPEN_REQUEST, Abo, Component, MatchStatus, RequestStatus, Rh, Role, SiteType, UnitStatus, Urgency
from app.core.errors import Problem
from app.modules.admin import service as settings
from app.modules.audit import service as audit
from app.modules.compatibility import service as compat
from app.modules.forecasting.models import Forecast
from app.modules.inventory import service as inventory
from app.modules.inventory.models import BloodUnit
from app.modules.matching import service as matching
from app.modules.matching.models import DonorMatch
from app.modules.matching.rules import km
from app.modules.notifications.service import notify
from app.modules.redistribution.models import TransferPlan, TransferRecommendation
from app.modules.requests.models import BloodRequest
from app.modules.sites.models import Site

STAFF_CONFIRM = {Role.hospital_lead, Role.bank_manager}


def get(db: Session, request_id: uuid.UUID) -> BloodRequest:
    r = db.get(BloodRequest, request_id)
    if not r:
        raise Problem(404, "not_found", "Request not found.")
    return r


def can_see(p: Principal, r: BloodRequest) -> bool:
    return r.requester_id == p.user_id or (p.role is not Role.requester and p.role is not Role.donor and p.can_see_site(r.site_id))


def view(db: Session, r: BloodRequest, p: Principal | None = None) -> dict[str, Any]:
    counts = dict(db.execute(select(DonorMatch.status, func.count()).where(DonorMatch.request_id == r.id).group_by(DonorMatch.status)).all())
    plan_id = db.scalar(select(TransferRecommendation.plan_id).join(TransferPlan, TransferPlan.id == TransferRecommendation.plan_id)
                        .where(TransferPlan.status == "request", TransferRecommendation.reason == f"request:{r.id}").limit(1))
    out: dict[str, Any] = {
        "id": r.id, "ref": r.ref, "kind": r.kind, "requester_id": r.requester_id, "site_id": r.site_id, "abo": r.abo, "rh": r.rh,
        "component": r.component, "units_needed": r.units_needed, "units_secured": r.units_secured, "urgency": r.urgency,
        "needed_by": r.needed_by, "status": r.status, "confirmed_at": r.confirmed_at, "created_at": r.created_at,
        "shortfall": r.shortfall, "wave": r.wave, "escalated_at": r.escalated_at, "transfer_plan_id": plan_id,
        "progress": {"stock_units": r.stock_units, "donors_notified": sum(counts.values()),
                     "donors_accepted": sum(n for s, n in counts.items() if s in (MatchStatus.accepted, MatchStatus.donated))},
        "accepted_matches": [],
    }
    if p is not None and r.requester_id == p.user_id:  # the requester can open chats with donors who accepted
        out["accepted_matches"] = [{"id": m.id, "status": m.status} for m in db.scalars(
            select(DonorMatch).where(DonorMatch.request_id == r.id, DonorMatch.status.in_([MatchStatus.accepted, MatchStatus.donated])))]
    return out


def create(db: Session, p: Principal, body: dict[str, Any]) -> BloodRequest:
    """FR-REQ-01. Requesters wait for hospital confirmation; staff requests for their own site confirm at once."""
    site = db.get(Site, body["site_id"])
    if not site or site.type is not SiteType.hospital or not site.active:
        raise Problem(422, "invalid_hospital", "Choose an active hospital.")
    if p.role is Role.requester:
        mine = select(func.count()).select_from(BloodRequest).where(BloodRequest.requester_id == p.user_id)
        if (db.scalar(mine.where(BloodRequest.status.in_(OPEN_REQUEST))) or 0) >= int(settings.get(db, "requester_open_limit")):
            raise Problem(429, "rate_limited", "You have reached the limit of open requests.")
        if (db.scalar(mine.where(BloodRequest.created_at > now() - timedelta(days=1))) or 0) >= int(settings.get(db, "requester_daily_limit")):
            raise Problem(429, "rate_limited", "You have reached today's request limit.")
    elif p.role is Role.hospital_lead:
        p.require_site(site.id)
    if body["needed_by"] <= now():
        raise Problem(422, "needed_by_past", "Needed-by time must be in the future.")
    r = BloodRequest(requester_id=p.user_id, site_id=site.id, abo=body["abo"], rh=body["rh"], component=body["component"],
                     units_needed=body["units_needed"], urgency=body["urgency"], needed_by=body["needed_by"], status=RequestStatus.submitted)
    db.add(r)
    db.flush()
    audit.record(db, p.user_id, "request.create", "blood_request", r.id, {"units": r.units_needed, "urgency": r.urgency})
    if p.role in STAFF_CONFIRM:
        _confirm(db, r, p)
    db.commit()
    return r


def confirm(db: Session, request_id: uuid.UUID, p: Principal) -> BloodRequest:
    r = db.scalars(select(BloodRequest).where(BloodRequest.id == request_id).with_for_update()).first()
    if not r:
        raise Problem(404, "not_found", "Request not found.")
    if p.role is not Role.hospital_lead or r.site_id not in p.site_ids:
        raise Problem(403, "out_of_scope", "Only a transfusion lead at this hospital can confirm.")  # FR-REQ-02
    if r.status is not RequestStatus.submitted:
        raise Problem(409, "invalid_transition", "Only submitted requests can be confirmed.")
    _confirm(db, r, p)
    db.commit()
    return r


def _confirm(db: Session, r: BloodRequest, p: Principal) -> None:
    """Network stock first (FR-REQ-03): reserve compatible units here, propose transfers from elsewhere, then match
    donors only for what is still missing (FR-REQ-04)."""
    r.status, r.confirmed_by, r.confirmed_at = RequestStatus.confirmed, p.user_id, now()
    audit.record(db, p.user_id, "request.confirm", "blood_request", r.id)
    donors_for = [(a, h) for a, h, _ in compat.donors_for(compat.rank_map(db), r.component, r.abo, r.rh)]
    need = r.units_needed
    local: list[BloodUnit] = []
    for a, h in donors_for:  # most preferred group first, then first-expired-first-out
        if len(local) >= need:
            break
        local += list(db.scalars(select(BloodUnit).where(BloodUnit.site_id == r.site_id, BloodUnit.status == UnitStatus.available,
                                                         BloodUnit.component == r.component, BloodUnit.abo == a, BloodUnit.rh == h,
                                                         BloodUnit.expires_at > now()).order_by(BloodUnit.expires_at).limit(need - len(local))))
    if local:
        inventory.apply_transition(db, inventory.lock_units(db, [u.id for u in local]), UnitStatus.reserved,
                                   f"Reserved for request {r.ref}", None, reserve_for=r.id)
    proposed = _propose_transfers(db, r, donors_for, need - len(local))
    r.units_secured, r.stock_units = len(local), len(local) + proposed
    r.shortfall = max(need - r.stock_units, 0)
    if r.shortfall == 0:
        r.status = RequestStatus.covered_by_stock  # no donor is contacted (FR-REQ-03)
    else:
        matching.start(db, r)
    notify(db, r.requester_id, "request_update", {"ref": r.ref, "status": r.status.value}, sms_too=False)


def _propose_transfers(db: Session, r: BloodRequest, groups: list[tuple[Abo, Rh]], need: int) -> int:
    """Compatible stock at other sites, nearest first, as recommendations a bank manager approves (spec section 2)."""
    if need <= 0:
        return 0
    site = db.get(Site, r.site_id)
    assert site is not None
    min_life = timedelta(days=int(settings.get(db, "min_transfer_life_days")[r.component.value]))
    others = sorted(db.scalars(select(Site).where(Site.active, Site.id != r.site_id)), key=lambda s: km((s.lat, s.lng), (site.lat, site.lng)))
    lines: list[tuple[Site, Abo, Rh, int]] = []
    left = need
    for s in others:
        for a, h in groups:
            if left <= 0:
                break
            n = db.scalar(select(func.count()).select_from(BloodUnit).where(
                BloodUnit.site_id == s.id, BloodUnit.status == UnitStatus.available, BloodUnit.component == r.component,
                BloodUnit.abo == a, BloodUnit.rh == h, BloodUnit.expires_at > now() + min_life)) or 0
            if n:
                take = min(n, left)
                lines.append((s, a, h, take))
                left -= take
    if not lines:
        return 0
    plan = TransferPlan(horizon_days=0, status="request", solver_status="REQUEST", solver_seconds=0, is_fallback=False,
                        projected={"request": str(r.id)})
    db.add(plan)
    db.flush()
    for s, a, h, n in lines:
        db.add(TransferRecommendation(plan_id=plan.id, from_site_id=s.id, to_site_id=r.site_id, component=r.component, abo=a, rh=h,
                                      units=n, reason=f"request:{r.id}", status="proposed",
                                      expected_benefit={"shortage_avoided": n, "expired_avoided": 0,
                                                        "km": round(km((s.lat, s.lng), (site.lat, site.lng)), 1)}))
    return need - left


def _release(db: Session, r: BloodRequest, reason: str) -> None:
    held = list(db.scalars(select(BloodUnit.id).where(BloodUnit.reserved_for == r.id, BloodUnit.status == UnitStatus.reserved)))
    if held:
        inventory.apply_transition(db, inventory.lock_units(db, held), UnitStatus.available, reason, None)
    db.execute(update(TransferRecommendation).where(TransferRecommendation.reason == f"request:{r.id}",
                                                    TransferRecommendation.status == "proposed").values(status="superseded"))
    matching.close(db, r)


def cancel(db: Session, request_id: uuid.UUID, p: Principal) -> BloodRequest:
    r = get(db, request_id)
    if not (r.requester_id == p.user_id or (p.role is Role.hospital_lead and r.site_id in p.site_ids) or p.role is Role.bank_manager):
        raise Problem(403, "forbidden", "You cannot cancel this request.")
    if r.status not in OPEN_REQUEST:
        raise Problem(409, "invalid_transition", "This request is already closed.")
    _release(db, r, f"Request {r.ref} cancelled")
    r.status = RequestStatus.cancelled
    audit.record(db, p.user_id, "request.cancel", "blood_request", r.id)
    db.commit()
    return r


def record_units(db: Session, request_id: uuid.UUID, units: int, p: Principal) -> BloodRequest:
    """Hospital records units received from donors (POST /requests/{id}/outcome)."""
    r = get(db, request_id)
    p.require_site(r.site_id)
    if r.status not in OPEN_REQUEST:
        raise Problem(409, "invalid_transition", "This request is already closed.")
    r.units_secured = min(r.units_needed, r.units_secured + units)
    if r.units_secured >= r.units_needed:
        r.status = RequestStatus.fulfilled
        matching.close(db, r)
    audit.record(db, p.user_id, "request.outcome", "blood_request", r.id, {"units": units})
    db.commit()
    return r


def close_overdue(db: Session) -> int:
    """Needed-by passed: fulfilled / partially fulfilled / unfilled (spec section 6 request states)."""
    n = 0
    for r in db.scalars(select(BloodRequest).where(BloodRequest.status.in_(OPEN_REQUEST), BloodRequest.needed_by <= now())):
        r.status = (RequestStatus.fulfilled if r.units_secured >= r.units_needed
                    else RequestStatus.partially_fulfilled if r.units_secured else RequestStatus.unfilled)
        if r.status is not RequestStatus.fulfilled:
            _release(db, r, f"Request {r.ref} closed")
        else:
            matching.close(db, r)
        notify(db, r.requester_id, "request_update", {"ref": r.ref, "status": r.status.value}, sms_too=False)
        n += 1
    db.commit()
    return n


# ----- low stock and appeals ---------------------------------------------------------------------------------------

def low_stock(db: Session) -> list[dict[str, Any]]:
    """Red-cell groups where on-hand stock is below forecast demand for the next N days (FR-ALR-02 rule)."""
    days = int(settings.get(db, "stock_alert_days"))
    today = now().date()
    out = []
    for site in db.scalars(select(Site).where(Site.active, Site.type == SiteType.hospital).order_by(Site.code)):
        run_id = db.scalar(select(Forecast.run_id).where(Forecast.site_id == site.id, Forecast.component == Component.red_cells)
                           .order_by(Forecast.created_at.desc(), Forecast.id.desc()).limit(1))
        if run_id is None:
            continue
        demand = {(a, h): float(v) for a, h, v in db.execute(select(Forecast.abo, Forecast.rh, func.sum(Forecast.point)).where(
            Forecast.run_id == run_id, Forecast.site_id == site.id, Forecast.component == Component.red_cells,
            Forecast.day >= today, Forecast.day < today + timedelta(days=days)).group_by(Forecast.abo, Forecast.rh))}
        stock = {(a, h): n for a, h, n in db.execute(select(BloodUnit.abo, BloodUnit.rh, func.count()).where(
            BloodUnit.site_id == site.id, BloodUnit.status == UnitStatus.available, BloodUnit.component == Component.red_cells,
            BloodUnit.expires_at > now()).group_by(BloodUnit.abo, BloodUnit.rh))}
        for (a, h), d in demand.items():
            have, need = stock.get((a, h), 0), math.floor(d + 0.5)  # whole units: ignore slivers of forecast demand
            if have < need:
                appeal = db.scalar(select(BloodRequest.id).where(BloodRequest.kind == "appeal", BloodRequest.site_id == site.id,
                                                                 BloodRequest.abo == a, BloodRequest.rh == h,
                                                                 BloodRequest.status.in_(OPEN_REQUEST)).limit(1))
                out.append({"site_id": site.id, "abo": a, "rh": h, "available": have, "demand": need,
                            "shortfall": need - have, "days": days, "open_appeal_id": appeal})
    return sorted(out, key=lambda x: (-x["shortfall"], str(x["site_id"])))


def appeal(db: Session, p: Principal, site_id: uuid.UUID, abo: Abo, rh: Rh, units: int, urgency: Urgency, hours: int | None) -> BloodRequest:
    """Staff ask eligible nearby donors to come and donate when stock runs low. A person always starts it."""
    site = db.get(Site, site_id)
    if not site or site.type is not SiteType.hospital:
        raise Problem(422, "invalid_hospital", "Choose a hospital.")
    if db.scalar(select(BloodRequest.id).where(BloodRequest.kind == "appeal", BloodRequest.site_id == site_id, BloodRequest.abo == abo,
                                               BloodRequest.rh == rh, BloodRequest.status.in_(OPEN_REQUEST)).limit(1)):
        raise Problem(409, "appeal_open", "An appeal for this group is already running at this site.")
    t: datetime = now()
    r = BloodRequest(requester_id=p.user_id, site_id=site_id, abo=abo, rh=rh, component=Component.red_cells, units_needed=units,
                     urgency=urgency, needed_by=t + timedelta(hours=hours or int(settings.get(db, "appeal_default_hours"))),
                     status=RequestStatus.confirmed, confirmed_by=p.user_id, confirmed_at=t, kind="appeal", shortfall=units)
    db.add(r)
    db.flush()
    audit.record(db, p.user_id, "appeal.create", "blood_request", r.id, {"units": units, "urgency": urgency})
    matching.start(db, r)
    db.commit()
    return r
