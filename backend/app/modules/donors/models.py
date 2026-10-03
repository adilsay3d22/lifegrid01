import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, Numeric, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base, UTCDateTime
from app.core.enums import Abo, Availability, Rh, db_enum


class Donor(Base):
    """Only what eligibility and matching need (SEC-07): no name, no address, no medical detail."""

    __tablename__ = "donor"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), unique=True)
    abo: Mapped[Abo | None] = mapped_column(db_enum(Abo, "abo_group"))
    rh: Mapped[Rh | None] = mapped_column(db_enum(Rh, "rh_factor"))
    group_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Rounded to 0.01 degrees (~1 km) before storing (FR-DON-01). Floats instead of geography: decision 0002.
    area_lat: Mapped[float | None] = mapped_column(Float)
    area_lng: Mapped[float | None] = mapped_column(Float)
    birth_year: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String)
    weight_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_donation_on: Mapped[date | None] = mapped_column(Date)
    availability: Mapped[Availability] = mapped_column(db_enum(Availability, "availability"), default=Availability.available)
    quiet_start: Mapped[time | None] = mapped_column(Time)
    quiet_end: Mapped[time | None] = mapped_column(Time)
    emergency_override: Mapped[bool] = mapped_column(Boolean, default=False)
    max_invites_30d: Mapped[int] = mapped_column(Integer, default=2)
    reliability: Mapped[float] = mapped_column(Numeric(4, 3), default=0.5)
    consent_version: Mapped[str]
    consent_at: Mapped[datetime] = mapped_column(UTCDateTime)
    reminded_for: Mapped[date | None] = mapped_column(Date)  # added: one reminder per eligibility date (FR-DON-04)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    @property
    def ref(self) -> str:
        return "D-" + self.id.hex[:6].upper()


class Deferral(Base):
    __tablename__ = "deferral"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    donor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donor.id"), index=True)
    category: Mapped[str]
    eligible_again_on: Mapped[date] = mapped_column(Date)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
