"""Donor matching: waves, responses, outcomes and masked messaging (FR-MAT-01..07)."""

import math
import uuid
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import Component, MatchStatus, RequestStatus, Role, Urgency
from app.core.errors import Problem
from app.core.security import decrypt
from app.modules.admin import service as settings
from app.modules.audit import service as audit
from app.modules.auth.models import AppUser
from app.modules.compatibility import service as compat
from app.modules.donors import service as donors
from app.modules.donors.models import Donor
from app.modules.matching.models import DonorMatch, Message, MessageThread
from app.modules.matching.rules import reliability as reliability_of
from app.modules.matching.rules import score, wave, why_not
from app.modules.notifications.service import notify
from app.modules.requests.models import BloodRequest
from app.modules.sites.models import Site

GROUP = {("O", "pos"): "O+", ("O", "neg"): "O−", ("A", "pos"): "A+", ("A", "neg"): "A−", ("B", "pos"): "B+", ("B", "neg"): "B−",
         ("AB", "pos"): "AB+", ("AB", "neg"): "AB−"}


def area_of(site: Site | None) -> str:
    """Coarse area for donors; never the hospital name (FR-MAT-03)."""
    return site.area if site and site.area else "a nearby hospital"


def group_label(abo: object, rh: object) -> str:
    return GROUP[(str(abo), str(rh))]


def _plan(db: Session, r: BloodRequest) -> dict[str, Any]:
    return dict(settings.get(db, "match_waves")[r.urgency.value])


def accepted(db: Session, r: BloodRequest) -> int:
    return db.scalar(select(func.count()).select_from(DonorMatch).where(
        DonorMatch.request_id == r.id, DonorMatch.status.in_([MatchStatus.accepted, MatchStatus.donated]))) or 0


def target(db: Session, r: BloodRequest) -> int:
    """Stop inviting once accepted donors cover the shortfall plus a margin (FR-MAT-05)."""
    return math.ceil(r.shortfall * (1 + float(settings.get(db, "match_coverage_margin"))))


def start(db: Session, r: BloodRequest) -> None:
    """Begin matching for the shortfall (FR-REQ-04). Only red cells match donors in v1 (spec 13.3)."""
    r.status, r.wave = RequestStatus.matching, 0
    if r.component is not Component.red_cells:
        escalate(db, r, "component_not_matched")
        return
    next_wave(db, r)


def next_wave(db: Session, r: BloodRequest) -> int:
    plan = _plan(db, r)
    if r.wave >= len(plan["radius_km"]):
        escalate(db, r, "no_donor_in_time")
        return 0
    radius = float(plan["radius_km"][r.wave])
    site = db.get(Site, r.site_id)
    assert site is not None
    t = now()
    ranks = compat.rank_map(db)
    compatible = {(da, dr) for da, dr, _ in compat.donors_for(ranks, Component.red_cells, r.abo, r.rh)}
    rules, weights = donors.rules(db), settings.get(db, "match_score_weights")
    local = t.astimezone(ZoneInfo(site.timezone))
    scored = []
    pool = donors.candidates(db, exclude_request=r.id)
    for _, c in pool:
        if why_not(c, compatible=compatible, site=(site.lat, site.lng), radius_km=radius, needed_by=r.needed_by.date(),
                   today=local.date(), local_time=local.time(), emergency=r.urgency is Urgency.emergency, rules=rules) is None:
            scored.append((c, score(c, recipient=(r.abo, r.rh), site=(site.lat, site.lng), radius_km=radius, at=t, weights=weights)))
    need = max(r.shortfall - accepted(db, r), 0)
    chosen = wave(scored, need, seed=str(r.id), margin=float(settings.get(db, "match_coverage_margin")))
    r.wave += 1
    r.next_wave_at = t + timedelta(minutes=int(plan["wait_minutes"]))
    by_id = {str(d.id): d for d, _ in pool}
    template = "appeal" if r.kind == "appeal" else "invite"
    payload = {"group": group_label(r.abo, r.rh), "area": area_of(site), "urgency": r.urgency.value}
    for c, s in chosen:
        d = by_id[c.id]
        db.add(DonorMatch(request_id=r.id, donor_id=d.id, wave=r.wave, score=s, status=MatchStatus.invited, invited_at=t))
        notify(db, d.user_id, template, payload)  # group, area, urgency only (FR-MAT-03)
    audit.record(db, None, "match.wave", "blood_request", r.id, {"wave": r.wave, "radius_km": radius, "invited": len(chosen),
                                                                 "eligible": len(scored)})
    return len(chosen)


def escalate(db: Session, r: BloodRequest, reason: str) -> None:
    """Tell coordinators and bank managers (FR-MAT-06). Alert records arrive with phase 7."""
    if r.escalated_at:
        return
    r.escalated_at, r.next_wave_at = now(), None
    site = db.get(Site, r.site_id)
    for u in db.scalars(select(AppUser).where(AppUser.role.in_([Role.donor_coordinator, Role.bank_manager]), AppUser.active)):
        notify(db, u.id, "escalation", {"ref": r.ref, "area": area_of(site), "waves": r.wave}, sms_too=False)
    audit.record(db, None, "match.escalate", "blood_request", r.id, {"reason": reason, "wave": r.wave})


def _stop(db: Session, r: BloodRequest) -> None:
    r.next_wave_at = None
    for m in db.scalars(select(DonorMatch).where(DonorMatch.request_id == r.id, DonorMatch.status == MatchStatus.invited)):
        m.status = MatchStatus.expired  # counts as an invitation without a response


def advance(db: Session) -> int:
    """Every minute: next wave where the wait has passed and acceptances still fall short (FR-MAT-02, 05, 06)."""
    n = 0
    due = select(BloodRequest).where(BloodRequest.status == RequestStatus.matching, BloodRequest.next_wave_at <= now())
    for r in db.scalars(due.with_for_update()):
        if accepted(db, r) >= target(db, r):
            _stop(db, r)
        else:
            next_wave(db, r)
        n += 1
    db.commit()
    return n


def close(db: Session, r: BloodRequest) -> None:
    _stop(db, r)


# ----- donor side ---------------------------------------------------------------------------------------------------

def _match_for(db: Session, match_id: uuid.UUID) -> tuple[DonorMatch, BloodRequest, Donor]:
    m = db.scalars(select(DonorMatch).where(DonorMatch.id == match_id).with_for_update()).first()
    if not m:
        raise Problem(404, "not_found", "Invitation not found.")
    r, d = db.get(BloodRequest, m.request_id), db.get(Donor, m.donor_id)
    assert r is not None and d is not None
    return m, r, d


def invitations(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    d = donors.mine(db, user_id)
    out = []
    for m, r, s in db.execute(select(DonorMatch, BloodRequest, Site).join(BloodRequest, BloodRequest.id == DonorMatch.request_id)
                              .join(Site, Site.id == BloodRequest.site_id).where(DonorMatch.donor_id == d.id)
                              .order_by(DonorMatch.invited_at.desc()).limit(50)):
        out.append({"id": m.id, "request_ref": r.ref, "abo": r.abo, "rh": r.rh, "hospital_area": area_of(s), "urgency": r.urgency,
                    "needed_by": r.needed_by, "status": m.status, "kind": r.kind})
    return out


def respond(db: Session, match_id: uuid.UUID, user_id: uuid.UUID, accept: bool) -> DonorMatch:
    m, r, d = _match_for(db, match_id)
    if d.user_id != user_id:
        raise Problem(404, "not_found", "Invitation not found.")
    if m.status is not MatchStatus.invited or r.status is not RequestStatus.matching:
        raise Problem(409, "invalid_transition", "This invitation is closed.")
    m.status, m.responded_at = (MatchStatus.accepted if accept else MatchStatus.declined), now()
    if accept:
        db.add(MessageThread(match_id=m.id))  # in-app thread; phones stay hidden until both opt in (FR-MAT-04)
        notify(db, r.requester_id, "donor_accepted", {"ref": r.ref}, sms_too=False)
        db.flush()
        if accepted(db, r) >= target(db, r):
            _stop(db, r)
    audit.record(db, user_id, "match.respond", "donor_match", m.id, {"accept": accept})
    db.commit()
    return m


def outcome(db: Session, match_id: uuid.UUID, result: MatchStatus, actor: uuid.UUID) -> DonorMatch:
    """Recorded by staff; the only thing that changes reliability (FR-MAT-07)."""
    if result not in (MatchStatus.donated, MatchStatus.no_show, MatchStatus.deferred_on_site):
        raise Problem(422, "invalid_outcome", "Outcome must be donated, no_show or deferred_on_site.")
    m, r, d = _match_for(db, match_id)
    if m.status is not MatchStatus.accepted:
        raise Problem(409, "invalid_transition", "Only accepted invitations get an outcome.")
    m.status, m.outcome_at = result, now()
    if result is MatchStatus.donated:
        d.last_donation_on = now().date()
        r.units_secured += 1
        if r.units_secured >= r.units_needed and r.status in (RequestStatus.matching, RequestStatus.covered_by_stock):
            r.status = RequestStatus.fulfilled
            _stop(db, r)
            notify(db, r.requester_id, "request_update", {"ref": r.ref, "status": "fulfilled"}, sms_too=False)
    db.flush()
    c = next((c for dd, c in donors.candidates(db) if dd.id == d.id), None)
    if c:
        d.reliability = round(reliability_of(c), 3)
    audit.record(db, actor, "match.outcome", "donor_match", m.id, {"outcome": result})
    db.commit()
    return m


# ----- messaging ----------------------------------------------------------------------------------------------------

def _thread(db: Session, match_id: uuid.UUID, user_id: uuid.UUID) -> tuple[MessageThread, str, DonorMatch, BloodRequest, Donor]:
    m, r, d = _match_for(db, match_id)
    side = "donor" if d.user_id == user_id else "requester" if r.requester_id == user_id else None
    t = db.scalar(select(MessageThread).where(MessageThread.match_id == m.id))
    if side is None or t is None:
        raise Problem(404, "not_found", "Conversation not found.")
    return t, side, m, r, d


def thread(db: Session, match_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
    t, side, m, r, d = _thread(db, match_id, user_id)
    site = db.get(Site, r.site_id)
    phone = None
    if t.donor_shares_phone and t.requester_shares_phone:  # SEC-08
        other = db.get(AppUser, r.requester_id if side == "donor" else d.user_id)
        phone = decrypt(other.phone_enc, get_settings().phone_enc_key) if other and other.phone_enc else None
    msgs = db.scalars(select(Message).where(Message.thread_id == t.id).order_by(Message.id))
    db.commit()  # release the row lock taken by _match_for
    return {"id": m.id, "request_ref": r.ref, "hospital_area": area_of(site), "role": side,
            "donor_shares_phone": t.donor_shares_phone, "requester_shares_phone": t.requester_shares_phone,
            "counterpart_phone": phone, "messages": [{"id": x.id, "mine": x.sender_id == user_id, "body": x.body, "created_at": x.created_at}
                                                     for x in msgs]}


def post_message(db: Session, match_id: uuid.UUID, user_id: uuid.UUID, body: str) -> None:
    t, *_ = _thread(db, match_id, user_id)
    db.add(Message(thread_id=t.id, sender_id=user_id, body=body[:1000]))
    db.commit()


def share_phone(db: Session, match_id: uuid.UUID, user_id: uuid.UUID) -> None:
    t, side, m, *_ = _thread(db, match_id, user_id)
    if side == "donor":
        t.donor_shares_phone = True
    else:
        t.requester_shares_phone = True
    audit.record(db, user_id, "match.share_phone", "donor_match", m.id, {"side": side})
    db.commit()


def request_matches(db: Session, request_id: uuid.UUID) -> list[dict[str, Any]]:
    """Staff view of a request's donors: reference, group, status — never contact details (SEC-08)."""
    rows = db.execute(select(DonorMatch, Donor).join(Donor, Donor.id == DonorMatch.donor_id)
                      .where(DonorMatch.request_id == request_id).order_by(DonorMatch.wave, DonorMatch.score.desc()))
    return [{"id": m.id, "donor_ref": d.ref, "abo": d.abo, "rh": d.rh, "group_verified": d.group_verified, "wave": m.wave,
             "score": float(m.score), "status": m.status, "invited_at": m.invited_at, "responded_at": m.responded_at} for m, d in rows]
