import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.db import get_db
from app.core.deps import STAFF, Principal, require
from app.core.enums import Abo, Component, Rh, Role, UnitStatus
from app.core.errors import Problem
from app.modules.auth.models import AppUser
from app.modules.inventory import service
from app.modules.inventory.models import BloodUnit, UnitMovement
from app.modules.inventory.rules import ACTIONS, DESTRUCTIVE
from app.modules.inventory.schemas import (
    BulkTransitionIn,
    ExcursionIn,
    ExcursionOut,
    ImportOut,
    MovementOut,
    ReceiveIn,
    StockCell,
    TransitionIn,
    TransitionOut,
    UnitDetail,
    UnitOut,
    UnitPage,
)

router = APIRouter(tags=["inventory"])
unit_writers = require(Role.bank_manager, Role.hospital_lead)
unit_readers = require(Role.bank_manager, Role.hospital_lead, Role.admin, Role.auditor)


@router.get("/stock/summary", response_model=list[StockCell])
def stock_summary(component: Component | None = None, _: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)) -> list[StockCell]:
    return service.stock_summary(db, component)


@router.get("/units", response_model=UnitPage)
def list_units(site_id: uuid.UUID, status: UnitStatus | None = None, component: Component | None = None,
               abo: Abo | None = None, rh: Rh | None = None, band: Literal["0_2", "3_7", "8"] | None = None,
               limit: int = Query(100, ge=1, le=500), cursor: str | None = None,
               p: Principal = Depends(unit_readers), db: Session = Depends(get_db)) -> UnitPage:
    p.require_site(site_id)
    q = select(BloodUnit).where(BloodUnit.site_id == site_id)
    if status:
        q = q.where(BloodUnit.status == status)
    if component:
        q = q.where(BloodUnit.component == component)
    if abo:
        q = q.where(BloodUnit.abo == abo)
    if rh:
        q = q.where(BloodUnit.rh == rh)
    if band:
        t = now()
        lo, hi = {"0_2": (None, 2), "3_7": (2, 7), "8": (7, None)}[band]
        if lo is not None:
            q = q.where(BloodUnit.expires_at > t + timedelta(days=lo))
        if hi is not None:
            q = q.where(BloodUnit.expires_at <= t + timedelta(days=hi))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    # Keyset pagination on (expires_at, id): first-expired first (FR-INV-09 ordering)
    q = q.order_by(BloodUnit.expires_at, BloodUnit.id)
    if cursor:
        u = db.get(BloodUnit, uuid.UUID(cursor))
        if u:
            q = q.where((BloodUnit.expires_at > u.expires_at) | ((BloodUnit.expires_at == u.expires_at) & (BloodUnit.id > u.id)))
    rows = list(db.scalars(q.limit(limit + 1)))
    return UnitPage(items=[UnitOut.model_validate(u) for u in rows[:limit]],
                    next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None, total=total)


@router.post("/units", response_model=UnitOut, status_code=201)
def receive_unit(body: ReceiveIn, p: Principal = Depends(unit_writers), db: Session = Depends(get_db)) -> UnitOut:
    return UnitOut.model_validate(service.receive(db, body.site_id, body, p))


@router.post("/units/import", response_model=ImportOut)
async def import_units(site_id: uuid.UUID = Form(...), file: UploadFile = File(...),
                       p: Principal = Depends(unit_writers), db: Session = Depends(get_db)) -> ImportOut:
    raw = await file.read(5_000_001)
    if len(raw) > 5_000_000:
        raise Problem(413, "file_too_large", "CSV must be under 5 MB.")
    r = service.import_csv(db, site_id, raw.decode("utf-8", errors="replace"), p)
    return ImportOut(imported=r.imported, errors=r.errors)


@router.get("/units/{unit_id}", response_model=UnitDetail)
def get_unit(unit_id: uuid.UUID, p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)) -> UnitDetail:
    u = db.get(BloodUnit, unit_id)
    if not u:
        raise Problem(404, "not_found", "Unit not found.")
    p.require_site(u.site_id)
    rows = db.execute(select(UnitMovement, AppUser.email).outerjoin(AppUser, AppUser.id == UnitMovement.actor_user_id)
                      .where(UnitMovement.unit_id == unit_id).order_by(UnitMovement.id))
    movements = [MovementOut.model_validate(m).model_copy(update={"actor": email or ("user" if m.actor_user_id else "system")}) for m, email in rows]
    return UnitDetail(unit=UnitOut.model_validate(u), movements=movements)


def _transition(ids: list[uuid.UUID], body: TransitionIn, p: Principal, db: Session) -> TransitionOut:
    if body.action in DESTRUCTIVE and len(body.reason.strip()) < 4:
        raise Problem(422, "reason_required", "Give a reason for this action.")
    units = service.transition(db, ids, ACTIONS[body.action], body.reason.strip() or body.action, p)
    return TransitionOut(changed=len(units))


@router.post("/units/{unit_id}/transition", response_model=TransitionOut)
def transition_one(unit_id: uuid.UUID, body: TransitionIn, p: Principal = Depends(unit_writers), db: Session = Depends(get_db)) -> TransitionOut:
    return _transition([unit_id], body, p, db)


@router.post("/units/transition", response_model=TransitionOut)
def transition_many(body: BulkTransitionIn, p: Principal = Depends(unit_writers), db: Session = Depends(get_db)) -> TransitionOut:
    return _transition(body.unit_ids, body, p, db)


@router.post("/excursions", response_model=ExcursionOut, status_code=201)
def record_excursion(body: ExcursionIn, p: Principal = Depends(unit_writers), db: Session = Depends(get_db)) -> ExcursionOut:
    ex, n = service.record_excursion(db, body, p)
    return ExcursionOut(id=ex.id, quarantined=n)
