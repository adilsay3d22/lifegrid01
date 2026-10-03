"""Inventory service: the only entry point for changing units (spec section 8 module boundaries).

Every state change: lock rows, validate the transition, write movement + audit event, commit once (spec section 10).
"""

import csv
import io
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.deps import Principal
from app.core.enums import Component
from app.core.enums import UnitStatus as S
from app.core.errors import Problem
from app.modules.audit import service as audit
from app.modules.inventory.models import BloodUnit, TemperatureExcursion, UnitMovement
from app.modules.inventory.rules import ALLOWED, SYSTEM, can
from app.modules.inventory.schemas import ExcursionIn, StockCell, UnitIn
from app.modules.sites.models import Site


def _actor(p: Principal | None) -> tuple[object, uuid.UUID | None]:
    return (p.role, p.user_id) if p else (SYSTEM, None)


def lock_units(db: Session, ids: Sequence[uuid.UUID]) -> list[BloodUnit]:
    """SELECT ... FOR UPDATE in id order (deadlock-free ordering). A no-op lock on SQLite."""
    rows = list(db.scalars(select(BloodUnit).where(BloodUnit.id.in_(ids)).order_by(BloodUnit.id).with_for_update()))
    if len(rows) != len(set(ids)):
        raise Problem(404, "not_found", "One or more units do not exist.")
    return rows


def apply_transition(db: Session, units: list[BloodUnit], to: S, reason: str, p: Principal | None, *,
                     transfer_id: uuid.UUID | None = None, to_site: uuid.UUID | None = None, check_scope: bool = True,
                     reserve_for: uuid.UUID | None = None) -> None:
    """Validate all, then change all. Caller owns the commit (so multi-step flows stay one transaction).
    check_scope=False only when the caller already authorised the site (e.g. the receiving site of a transfer)."""
    role, user_id = _actor(p)
    for u in units:
        if p and check_scope:
            p.require_site(u.site_id)
        if (u.status, to) not in ALLOWED:
            raise Problem(409, "invalid_transition", f"{u.unit_code}: a {u.status.value} unit cannot become {to.value}.")
        if not can(u.status, to, role):  # type: ignore[arg-type]
            raise Problem(403, "forbidden_role", f"{u.unit_code}: your role cannot make a {u.status.value} unit {to.value}.")
    for u in units:
        frm, site = u.status, u.site_id
        u.status = to
        u.version += 1
        if frm is S.reserved:
            u.reserved_for = None
        if to is S.reserved:
            if reserve_for is None:
                raise Problem(422, "reservation_needs_request", "A reservation must name the request.")
            u.reserved_for = reserve_for  # set with the status so the CHECK constraint holds at flush
        if to_site is not None:
            u.site_id = to_site  # location changes only here, i.e. on receipt (FR-RD-05)
        db.add(UnitMovement(unit_id=u.id, from_status=frm, to_status=to, from_site_id=site, to_site_id=u.site_id,
                            transfer_id=transfer_id, actor_user_id=user_id, reason=reason, created_at=now()))
        audit.record(db, user_id, "unit.transition", "blood_unit", u.id, {"from": frm, "to": to, "reason": reason})


def transition(db: Session, ids: list[uuid.UUID], to: S, reason: str, p: Principal) -> list[BloodUnit]:
    units = lock_units(db, ids)
    apply_transition(db, units, to, reason, p)
    db.commit()
    return units


def _check_new(db: Session, n: UnitIn) -> str | None:
    if db.scalar(select(BloodUnit.id).where(BloodUnit.unit_code == n.unit_code)):
        return "duplicate_code"
    return None


def _add(db: Session, n: UnitIn, site_id: uuid.UUID, p: Principal) -> BloodUnit:
    u = BloodUnit(unit_code=n.unit_code, abo=n.abo, rh=n.rh, component=n.component, collected_at=n.collected_at,
                  expires_at=n.expires_at, site_id=site_id, status=S.available)
    db.add(u)
    db.flush()
    db.add(UnitMovement(unit_id=u.id, from_status=None, to_status=S.available, to_site_id=site_id,
                        actor_user_id=p.user_id, reason="Received at site", created_at=now()))
    audit.record(db, p.user_id, "unit.receive", "blood_unit", u.id, {"site": site_id, "code": n.unit_code})
    return u


def receive(db: Session, site_id: uuid.UUID, n: UnitIn, p: Principal) -> BloodUnit:
    p.require_site(site_id)
    if not db.get(Site, site_id):
        raise Problem(404, "not_found", "Site not found.")
    if _check_new(db, n):
        raise Problem(409, "duplicate_code", "A unit with this code already exists.")
    u = _add(db, n, site_id, p)
    db.commit()
    return u


@dataclass
class ImportReport:
    imported: int
    errors: list[dict[str, object]]


REQUIRED = ["unit_code", "abo", "rh", "component", "collected_at", "expires_at"]


def import_csv(db: Session, site_id: uuid.UUID, text: str, p: Principal) -> ImportReport:
    """Good rows import, bad rows are reported by row number and reason (FR-INV-08)."""
    p.require_site(site_id)
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise Problem(422, "bad_header", f"Missing columns: {', '.join(missing)}", missing=missing)
    errors: list[dict[str, object]] = []
    seen: set[str] = set()
    good = 0
    for i, row in enumerate(reader, start=2):
        try:
            n = UnitIn.model_validate({k: (row.get(k) or "").strip() for k in REQUIRED})
        except ValidationError as e:
            err = e.errors()[0]
            reason = "expiry_before_collection" if "expiry_before_collection" in err["msg"] else (
                f"invalid_{err['loc'][0]}" if err["loc"] else "invalid_row")
            errors.append({"row": i, "reason": reason})
            continue
        if n.unit_code in seen or _check_new(db, n):
            errors.append({"row": i, "reason": "duplicate_code"})
            continue
        seen.add(n.unit_code)
        _add(db, n, site_id, p)
        good += 1
    audit.record(db, p.user_id, "unit.import", "site", site_id, {"imported": good, "rejected": len(errors)})
    db.commit()
    return ImportReport(good, errors)


def release_stale_reservations(db: Session, hours: int) -> int:
    """Reservations not issued within the timeout go back to available (FR-INV-06)."""
    ids = list(db.scalars(select(BloodUnit.id).where(BloodUnit.status == S.reserved, BloodUnit.updated_at <= now() - timedelta(hours=hours))))
    if ids:
        apply_transition(db, lock_units(db, ids), S.available, "Reservation timed out", None)
        db.commit()
    return len(ids)


def expire_overdue(db: Session) -> int:
    """Scheduled every 15 minutes (FR-INV-04)."""
    ids = list(db.scalars(select(BloodUnit.id).where(BloodUnit.status.in_([S.available, S.reserved, S.in_transit]),
                                                    BloodUnit.expires_at <= now())))
    if ids:
        apply_transition(db, lock_units(db, ids), S.expired, "Expiry time passed", None)
        db.commit()
    return len(ids)


def record_excursion(db: Session, body: ExcursionIn, p: Principal) -> tuple[TemperatureExcursion, int]:
    """Record an excursion and quarantine affected units (FR-INV-07)."""
    if body.site_id:
        p.require_site(body.site_id)
    ex = TemperatureExcursion(site_id=body.site_id, transfer_id=body.transfer_id, component=body.component,
                              started_at=body.started_at, ended_at=body.ended_at, min_c=body.min_c, max_c=body.max_c, recorded_by=p.user_id)
    db.add(ex)
    db.flush()
    if body.transfer_id:
        ids = list(db.scalars(select(UnitMovement.unit_id).where(UnitMovement.transfer_id == body.transfer_id)))
        q = select(BloodUnit.id).where(BloodUnit.id.in_(ids), BloodUnit.status == S.in_transit)
    else:
        q = select(BloodUnit.id).where(BloodUnit.site_id == body.site_id, BloodUnit.component == body.component,
                                       BloodUnit.status.in_([S.available, S.reserved]))
    affected = list(db.scalars(q))
    if affected:
        apply_transition(db, lock_units(db, affected), S.quarantined, f"Temperature excursion {ex.id}", p)
    audit.record(db, p.user_id, "excursion.record", "temperature_excursion", ex.id, {"units": len(affected)})
    db.commit()
    return ex, len(affected)


def stock_summary(db: Session, component: Component | None) -> list[StockCell]:
    """Available units by site, component, group and days-to-expiry band (FR-INV-05)."""
    q = select(BloodUnit.site_id, BloodUnit.component, BloodUnit.abo, BloodUnit.rh, BloodUnit.expires_at).where(BloodUnit.status == S.available)
    if component:
        q = q.where(BloodUnit.component == component)
    t = now()
    cells: dict[tuple[object, ...], list[int]] = defaultdict(lambda: [0, 0, 0])
    for site, comp, abo, rh, exp in db.execute(q):
        d = (exp - t) / timedelta(days=1)
        cells[(site, comp, abo, rh)][0 if d <= 2 else 1 if d <= 7 else 2] += 1
    return [StockCell(site_id=k[0], component=k[1], abo=k[2], rh=k[3], band_0_2=v[0], band_3_7=v[1], band_8=v[2])  # type: ignore[arg-type]
            for k, v in cells.items()]
