import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base, BigId, UTCDateTime
from app.core.enums import Abo, Component, Rh, db_enum


class UsageDaily(Base):
    __tablename__ = "usage_daily"
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    component: Mapped[Component] = mapped_column(db_enum(Component, "component"), primary_key=True)
    abo: Mapped[Abo] = mapped_column(db_enum(Abo, "abo_group"), primary_key=True)
    rh: Mapped[Rh] = mapped_column(db_enum(Rh, "rh_factor"), primary_key=True)
    units_used: Mapped[int] = mapped_column(Integer)


class Forecast(Base):
    __tablename__ = "forecast"
    __table_args__ = (
        CheckConstraint("low <= point AND point <= high", name="forecast_band_order"),
        Index("ix_forecast_series", "site_id", "component", "abo", "rh", "day"),
    )
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"))
    day: Mapped[date] = mapped_column(Date)
    component: Mapped[Component] = mapped_column(db_enum(Component, "component"))
    abo: Mapped[Abo] = mapped_column(db_enum(Abo, "abo_group"))
    rh: Mapped[Rh] = mapped_column(db_enum(Rh, "rh_factor"))
    point: Mapped[float] = mapped_column(Numeric(8, 2))
    low: Mapped[float] = mapped_column(Numeric(8, 2))
    high: Mapped[float] = mapped_column(Numeric(8, 2))
    model: Mapped[str]
    model_version: Mapped[str]
    backtest_mae: Mapped[float] = mapped_column(Numeric(8, 3))  # added: error stored with each forecast (FR-FC-03)
    baseline_mae: Mapped[float] = mapped_column(Numeric(8, 3))  # added: seasonal-naive error, for comparison
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
