import uuid

from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.enums import SiteType, db_enum


class Site(Base):
    __tablename__ = "site"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str]
    type: Mapped[SiteType] = mapped_column(db_enum(SiteType, "site_type"))
    # ponytail: lat/lng floats + haversine instead of PostGIS geography; fine to ~100 sites (decision 0002).
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(default="Asia/Dhaka")
    area: Mapped[str | None]  # added: coarse area shown to donors instead of the hospital (FR-MAT-03)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
