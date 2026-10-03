import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base, BigId, UTCDateTime
from app.core.enums import Abo, Component, Rh, UnitStatus, db_enum


class BloodUnit(Base):
    __tablename__ = "blood_unit"
    __table_args__ = (
        CheckConstraint("expires_at > collected_at", name="expiry_after_collection"),
        CheckConstraint("(status = 'reserved') = (reserved_for IS NOT NULL)", name="reserved_has_request"),
        Index("ix_unit_pick", "site_id", "component", "abo", "rh", "status", "expires_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    unit_code: Mapped[str] = mapped_column(String, unique=True)
    abo: Mapped[Abo] = mapped_column(db_enum(Abo, "abo_group"))
    rh: Mapped[Rh] = mapped_column(db_enum(Rh, "rh_factor"))
    component: Mapped[Component] = mapped_column(db_enum(Component, "component"))
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"))
    status: Mapped[UnitStatus] = mapped_column(db_enum(UnitStatus, "unit_status"), default=UnitStatus.available)
    reserved_for: Mapped[uuid.UUID | None]
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now, onupdate=now)


class Transfer(Base):
    __tablename__ = "transfer"
    __table_args__ = (CheckConstraint("from_site_id <> to_site_id", name="transfer_distinct_sites"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID | None]
    from_site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"))
    to_site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"))
    # Added (decision 0002): the approved line, so dispatch can pick without re-reading the recommendation.
    component: Mapped[Component] = mapped_column(db_enum(Component, "component"))
    abo: Mapped[Abo] = mapped_column(db_enum(Abo, "abo_group"))
    rh: Mapped[Rh] = mapped_column(db_enum(Rh, "rh_factor"))
    units: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # approved, dispatched, received, cancelled
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    dispatched_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class UnitMovement(Base):
    __tablename__ = "unit_movement"
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("blood_unit.id"), index=True)
    from_status: Mapped[UnitStatus | None] = mapped_column(db_enum(UnitStatus, "unit_status"))
    to_status: Mapped[UnitStatus] = mapped_column(db_enum(UnitStatus, "unit_status"))
    from_site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("site.id"))
    to_site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("site.id"))
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transfer.id"), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    reason: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class TemperatureExcursion(Base):
    __tablename__ = "temperature_excursion"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("site.id"))
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transfer.id"))
    component: Mapped[Component] = mapped_column(db_enum(Component, "component"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    min_c: Mapped[float | None] = mapped_column(Numeric(5, 2))
    max_c: Mapped[float | None] = mapped_column(Numeric(5, 2))
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
