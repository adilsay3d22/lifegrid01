"""Donor profiles, eligibility data and privacy actions (FR-DON-01..07)."""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import ACCEPTED_LIKE, Abo, MatchStatus, Rh
from app.core.errors import Problem
from app.modules.admin import service as settings
from app.modules.audit import service as audit
from app.modules.auth.models import AppUser, RefreshToken
from app.modules.donors.models import Deferral, Donor
from app.modules.matching.models import DonorMatch
from app.modules.matching.rules import Candidate, Rules, eligible_from, km
from app.modules.notifications.service import notify
from app.modules.sites.models import Site

CONSENT_VERSION = "v1.2"


def rules(db: Session) -> Rules:
    return Rules(cooldown_days=int(settings.get(db, "donor_cooldown_days")), age_min=int(settings.get(db, "donor_age_min")),
                 age_max=int(settings.get(db, "donor_age_max")))


def round_area(v: float | None) -> float | None:
    return None if v is None else round(v, 2)  # ~1 km (FR-DON-01)


def active_deferral(db: Session, donor_id: uuid.UUID, today: date) -> Deferral | None:
    return db.scalar(select(Deferral).where(Deferral.donor_id == donor_id, Deferral.eligible_again_on > today)
                     .order_by(Deferral.eligible_again_on.desc()).limit(1))


def area_label(db: Session, d: Donor) -> str:
    if d.area_lat is None or d.area_lng is None:
        return "—"
    sites = list(db.scalars(select(Site).where(Site.active)))
    if not sites:
        return f"{d.area_lat:.2f}, {d.area_lng:.2f}"
    s = min(sites, key=lambda s: km((d.area_lat, d.area_lng), (s.lat, s.lng)))  # type: ignore[arg-type]
    return s.area or s.name


def view(db: Session, d: Donor) -> dict[str, Any]:
    today = now().date()
    defer = active_deferral(db, d.id, today)
    nxt = eligible_from(d.last_donation_on, defer.eligible_again_on if defer else None, rules(db).cooldown_days)
    return {"id": d.id, "ref": d.ref, "abo": d.abo, "rh": d.rh, "group_verified": d.group_verified, "area_label": area_label(db, d),
            "area_lat": d.area_lat, "area_lng": d.area_lng, "birth_year": d.birth_year, "weight_ok": d.weight_ok,
            "last_donation_on": d.last_donation_on, "availability": d.availability, "reliability": float(d.reliability),
            "deferral": {"category": defer.category, "eligible_again_on": defer.eligible_again_on} if defer else None,
            "eligible_from": nxt if nxt and nxt > today else None, "quiet_start": d.quiet_start, "quiet_end": d.quiet_end,
            "emergency_override": d.emergency_override, "max_invites_30d": d.max_invites_30d,
            "consent_version": d.consent_version, "consent_at": d.consent_at}


def mine(db: Session, user_id: uuid.UUID) -> Donor:
    d = db.scalar(select(Donor).where(Donor.user_id == user_id, Donor.deleted_at.is_(None)))
    if not d:
        raise Problem(404, "not_registered", "Complete donor registration first.")
    return d


def upsert(db: Session, user_id: uuid.UUID, body: dict[str, Any]) -> Donor:
    """First call registers (consent required, FR-DON-01); later calls update the profile and availability."""
    d = db.scalar(select(Donor).where(Donor.user_id == user_id, Donor.deleted_at.is_(None)))
    if d is None:
        if not body.get("consent"):
            raise Problem(422, "consent_required", "You need to agree to the consent text to register.")
        if body.get("area_lat") is None or body.get("area_lng") is None:
            raise Problem(422, "area_required", "Set your area on the map.")
        d = Donor(user_id=user_id, consent_version=body.get("consent_version") or CONSENT_VERSION, consent_at=now(),
                  max_invites_30d=int(settings.get(db, "max_invites_per_30d")))
        db.add(d)
        created = True
    else:
        created = False
    for k in ("abo", "rh", "birth_year", "weight_ok", "availability", "quiet_start", "quiet_end", "emergency_override", "max_invites_30d"):
        if k in body:
            setattr(d, k, body[k])
    if "abo" in body or "rh" in body:
        d.group_verified = False  # self-reported until a coordinator verifies (FR-DON-07)
    if "area_lat" in body:
        d.area_lat, d.area_lng = round_area(body["area_lat"]), round_area(body.get("area_lng"))
    db.flush()
    audit.record(db, user_id, "donor.register" if created else "donor.update", "donor", d.id,
                 {k: v for k, v in body.items() if k not in ("area_lat", "area_lng")})
    db.commit()
    return d


def export(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    d = mine(db, user_id)
    matches = db.scalars(select(DonorMatch).where(DonorMatch.donor_id == d.id).order_by(DonorMatch.invited_at))
    out = {"exported_at": now(), "profile": view(db, d),
           "invitations": [{"status": m.status, "invited_at": m.invited_at, "responded_at": m.responded_at} for m in matches]}
    audit.record(db, user_id, "donor.export", "donor", d.id)
    db.commit()
    return out


def delete(db: Session, user_id: uuid.UUID) -> None:
    """Remove personal fields; keep only the anonymous row so counts stay correct (FR-DON-06, SEC-15)."""
    d = mine(db, user_id)
    for k in ("abo", "rh", "area_lat", "area_lng", "birth_year", "sex", "weight_ok", "last_donation_on", "quiet_start", "quiet_end"):
        setattr(d, k, None)
    d.deleted_at = now()
    u = db.get(AppUser, user_id)
    if u:
        u.phone_enc, u.phone_hash, u.active = None, f"deleted:{uuid.uuid4().hex}", False
        db.execute(update(RefreshToken).where(RefreshToken.user_id == u.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now()))
    for m in db.scalars(select(DonorMatch).where(DonorMatch.donor_id == d.id, DonorMatch.status.in_([MatchStatus.invited, MatchStatus.accepted]))):
        m.status = MatchStatus.withdrawn if m.status is MatchStatus.accepted else MatchStatus.expired
    audit.record(db, user_id, "donor.delete", "donor", d.id)
    db.commit()


def search(db: Session, group: str | None, eligible: str | None, q: str | None) -> list[Donor]:
    stmt = select(Donor).where(Donor.deleted_at.is_(None))
    if group:
        stmt = stmt.where(Donor.abo == Abo(group.removesuffix("pos").removesuffix("neg")), Donor.rh == Rh("neg" if group.endswith("neg") else "pos"))
    donors = list(db.scalars(stmt.order_by(Donor.consent_at.desc()).limit(2000)))
    if q:
        donors = [d for d in donors if q.lower() in d.ref.lower()]
    if eligible:
        today, r = now().date(), rules(db)
        defer = dict(db.execute(select(Deferral.donor_id, func.max(Deferral.eligible_again_on)).group_by(Deferral.donor_id)).all())
        ok = {d.id for d in donors if (eligible_from(d.last_donation_on, defer.get(d.id), r.cooldown_days) or today) <= today}
        donors = [d for d in donors if (d.id in ok) == (eligible == "yes")]
    return donors


def add_deferral(db: Session, donor_id: uuid.UUID, category: str, until: date, actor: uuid.UUID) -> None:
    d = db.get(Donor, donor_id)
    if not d or d.deleted_at:
        raise Problem(404, "not_found", "Donor not found.")
    if until <= now().date():
        raise Problem(422, "future_date", "Eligible-again date must be in the future.")
    db.add(Deferral(donor_id=d.id, category=category, eligible_again_on=until, recorded_by=actor))
    audit.record(db, actor, "donor.deferral", "donor", d.id, {"category": category, "until": until})
    db.commit()


def verify_group(db: Session, donor_id: uuid.UUID, actor: uuid.UUID) -> None:
    d = db.get(Donor, donor_id)
    if not d or d.deleted_at or d.abo is None:
        raise Problem(404, "not_found", "Donor not found or group unknown.")
    d.group_verified = True
    audit.record(db, actor, "donor.verify_group", "donor", d.id)
    db.commit()


def candidates(db: Session, exclude_request: uuid.UUID | None = None) -> list[tuple[Donor, Candidate]]:
    """Every live donor with the history matching needs (counts from donor_match; spec 13.3)."""
    t = now()
    stats: dict[uuid.UUID, dict[str, Any]] = defaultdict(lambda: {"inv": 0, "resp": 0, "acc": 0, "don": 0, "inv30": 0, "last": None})
    for donor_id, status, invited_at in db.execute(select(DonorMatch.donor_id, DonorMatch.status, DonorMatch.invited_at)):
        s = stats[donor_id]
        s["inv"] += 1
        s["resp"] += status not in (MatchStatus.invited, MatchStatus.expired)
        s["acc"] += status in ACCEPTED_LIKE
        s["don"] += status is MatchStatus.donated
        s["inv30"] += invited_at > t - timedelta(days=30)
        s["last"] = max(filter(None, [s["last"], invited_at]), default=None)
    already = set(db.scalars(select(DonorMatch.donor_id).where(DonorMatch.request_id == exclude_request))) if exclude_request else set()
    defer = dict(db.execute(select(Deferral.donor_id, func.max(Deferral.eligible_again_on)).group_by(Deferral.donor_id)).all())
    out = []
    for d in db.scalars(select(Donor).where(Donor.deleted_at.is_(None))):
        if d.id in already:
            continue
        s = stats[d.id]
        out.append((d, Candidate(str(d.id), d.abo, d.rh, d.group_verified, d.area_lat, d.area_lng, d.birth_year, d.weight_ok,
                                 d.last_donation_on, defer.get(d.id), d.availability, d.quiet_start, d.quiet_end, d.emergency_override,
                                 d.max_invites_30d, s["inv30"], s["inv"], s["resp"], s["acc"], s["don"], s["last"])))
    return out


def remind_eligible(db: Session) -> int:
    """Once per eligibility date, tell donors they can donate again (FR-DON-04)."""
    today, r, n = now().date(), rules(db), 0
    defer = dict(db.execute(select(Deferral.donor_id, func.max(Deferral.eligible_again_on)).group_by(Deferral.donor_id)).all())
    for d in db.scalars(select(Donor).where(Donor.deleted_at.is_(None), Donor.last_donation_on.is_not(None))):
        nxt = eligible_from(d.last_donation_on, defer.get(d.id), r.cooldown_days)
        if nxt == today and d.reminded_for != today:
            notify(db, d.user_id, "eligible_again", {})
            d.reminded_for = today
            n += 1
    db.commit()
    return n
