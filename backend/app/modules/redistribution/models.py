import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base, JSONType, UTCDateTime
from app.core.enums import Abo, Component, Rh, db_enum


class TransferPlan(Base):
    __tablename__ = "transfer_plan"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    horizon_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # proposed, reviewed, expired
    solver_status: Mapped[str]
    solver_seconds: Mapped[float | None] = mapped_column(Numeric(8, 2))
    is_fallback: Mapped[bool] = mapped_column(Boolean)
    projected: Mapped[dict[str, Any]] = mapped_column(JSONType)


class TransferRecommendation(Base):
    __tablename__ = "transfer_recommendation"
    __table_args__ = (CheckConstraint("units > 0", name="rec_units_positive"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transfer_plan.id"), index=True)
    from_site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"))
    to_site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"))
    component: Mapped[Component] = mapped_column(db_enum(Component, "component"))
    abo: Mapped[Abo] = mapped_column(db_enum(Abo, "abo_group"))
    rh: Mapped[Rh] = mapped_column(db_enum(Rh, "rh_factor"))
    units: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str]
    expected_benefit: Mapped[dict[str, Any]] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String)  # proposed, approved, rejected, superseded
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
