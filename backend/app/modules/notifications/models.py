import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base, JSONType, UTCDateTime


class Notification(Base):
    __tablename__ = "notification"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), index=True)
    channel: Mapped[str]  # in_app | sms | email
    template: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)  # added: template variables, no contact details
    status: Mapped[str]  # sent | failed | unread | read
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=now)
    error: Mapped[str | None]
