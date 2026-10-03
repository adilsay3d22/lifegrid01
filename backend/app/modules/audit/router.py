import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import Principal, require
from app.core.enums import Role
from app.modules.audit import service
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AppUser

router = APIRouter(prefix="/audit", tags=["audit"])
admin_or_auditor = require(Role.admin, Role.auditor)


class AuditOut(BaseModel):
    id: int
    actor_user_id: uuid.UUID | None
    actor: str
    action: str
    entity_type: str
    entity_id: str
    data: dict[str, Any]
    created_at: datetime
    hash: str


class AuditPage(BaseModel):
    items: list[AuditOut]
    next_cursor: int | None


class ChainOut(BaseModel):
    ok: bool
    checked: int
    broken_at: int | None


@router.get("", response_model=AuditPage)
def search(q: str = "", limit: int = Query(50, ge=1, le=200), cursor: int | None = None,
           _: Principal = Depends(admin_or_auditor), db: Session = Depends(get_db)) -> AuditPage:
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit + 1)
    if cursor:
        stmt = stmt.where(AuditEvent.id < cursor)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(AuditEvent.action.ilike(like), AuditEvent.entity_id.ilike(like), AuditEvent.entity_type.ilike(like)))
    rows = list(db.scalars(stmt))
    emails = dict(db.execute(select(AppUser.id, AppUser.email).where(AppUser.id.in_({e.actor_user_id for e in rows if e.actor_user_id}))).all())
    items = [AuditOut(id=e.id, actor_user_id=e.actor_user_id, actor=(emails.get(e.actor_user_id) or "user") if e.actor_user_id else "system",
                      action=e.action, entity_type=e.entity_type, entity_id=e.entity_id, data=e.data, created_at=e.created_at,
                      hash=e.hash.hex()[:16]) for e in rows[:limit]]
    return AuditPage(items=items, next_cursor=rows[limit - 1].id if len(rows) > limit else None)


@router.get("/verify", response_model=ChainOut)
def verify(p: Principal = Depends(admin_or_auditor), db: Session = Depends(get_db)) -> ChainOut:
    r = service.verify(db)
    service.record(db, p.user_id, "audit.verify", "audit_event", r.checked, {"ok": r.ok, "broken_at": r.broken_at})
    db.commit()
    return ChainOut(ok=r.ok, checked=r.checked, broken_at=r.broken_at)
