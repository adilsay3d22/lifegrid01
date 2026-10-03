import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base, BigId, JSONType, UTCDateTime


class Setting(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType)
    version: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class SettingHistory(Base):
    __tablename__ = "setting_history"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    key: Mapped[str]
    old_value: Mapped[Any | None] = mapped_column(JSONType)
    new_value: Mapped[Any] = mapped_column(JSONType)
    version: Mapped[int]
    changed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
