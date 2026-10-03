import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigId, JSONType, UTCDateTime


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[uuid.UUID | None]
    action: Mapped[str]
    entity_type: Mapped[str]
    entity_id: Mapped[str]
    data: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary)
    hash: Mapped[bytes] = mapped_column(LargeBinary)
