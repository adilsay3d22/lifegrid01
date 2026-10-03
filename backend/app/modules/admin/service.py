"""Versioned business settings (FR-ADM-02). Code reads rules through get(); defaults come from config."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import BUSINESS_DEFAULTS
from app.core.errors import Problem
from app.modules.admin.models import Setting, SettingHistory
from app.modules.audit import service as audit


def get(db: Session, key: str) -> Any:
    row = db.get(Setting, key)
    if row is not None:
        return row.value
    if key not in BUSINESS_DEFAULTS:
        raise KeyError(key)
    return BUSINESS_DEFAULTS[key]


def seed(db: Session) -> None:
    have = set(db.scalars(select(Setting.key)))
    for k, v in BUSINESS_DEFAULTS.items():
        if k not in have:
            db.add(Setting(key=k, value=v, version=1, updated_at=now()))


def put(db: Session, key: str, value: Any, actor: uuid.UUID) -> Setting:
    if key not in BUSINESS_DEFAULTS:
        raise Problem(404, "unknown_setting", f"No setting named {key}.")
    default = BUSINESS_DEFAULTS[key]
    if type(value) is not type(default) and not (isinstance(default, float) and isinstance(value, int)):
        raise Problem(422, "invalid_setting", f"{key} must be a {type(default).__name__}.")
    if isinstance(default, dict) and set(value) != set(default):
        raise Problem(422, "invalid_setting", f"{key} must have keys {sorted(default)}.")
    row = db.get(Setting, key)
    old = row.value if row else None
    if row is None:
        row = Setting(key=key, value=value, version=1)
        db.add(row)
    else:
        row.value, row.version = value, row.version + 1
    row.updated_by, row.updated_at = actor, now()
    db.add(SettingHistory(key=key, old_value=old, new_value=value, version=row.version, changed_by=actor, changed_at=now()))
    audit.record(db, actor, "setting.change", "setting", key, {"old": old, "new": value, "version": row.version})
    db.commit()
    return row
