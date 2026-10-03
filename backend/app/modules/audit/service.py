"""Hash-chained audit log (FR-AUD-01/02). Callers write the event in the same transaction as the change."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.db import advisory_lock
from app.modules.audit.models import AuditEvent

GENESIS = b"\x00" * 32
_LOCK_KEY = 0x4C47_4155  # "LGAU"


def _canonical(actor: uuid.UUID | None, action: str, entity_type: str, entity_id: str, data: dict[str, Any], at: datetime) -> bytes:
    body = {"actor": str(actor) if actor else None, "action": action, "entity_type": entity_type,
            "entity_id": entity_id, "data": data, "at": at.astimezone(UTC).isoformat()}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()


def record(db: Session, actor: uuid.UUID | None, action: str, entity_type: str, entity_id: object,
           data: dict[str, Any] | None = None) -> AuditEvent:
    """Append one event. Serialised by an advisory lock so each event reads the true previous hash."""
    advisory_lock(db, _LOCK_KEY)
    prev = db.scalar(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)) or GENESIS
    clean = json.loads(json.dumps(data or {}, default=str))  # store exactly what we hash
    at = now()
    ev = AuditEvent(actor_user_id=actor, action=action, entity_type=entity_type, entity_id=str(entity_id), data=clean,
                    created_at=at, prev_hash=prev,
                    hash=hashlib.sha256(prev + _canonical(actor, action, entity_type, str(entity_id), clean, at)).digest())
    db.add(ev)
    db.flush()
    return ev


@dataclass
class ChainCheck:
    ok: bool
    checked: int
    broken_at: int | None


def verify(db: Session) -> ChainCheck:
    prev = GENESIS
    n = 0
    for ev in db.scalars(select(AuditEvent).order_by(AuditEvent.id)).yield_per(1000):
        expected = hashlib.sha256(prev + _canonical(ev.actor_user_id, ev.action, ev.entity_type, ev.entity_id, ev.data, ev.created_at)).digest()
        if ev.prev_hash != prev or ev.hash != expected:
            return ChainCheck(False, n, ev.id)
        prev = ev.hash
        n += 1
    return ChainCheck(True, n, None)
