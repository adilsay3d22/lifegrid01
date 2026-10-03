import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base, UTCDateTime
from app.core.enums import Abo, Component, RequestStatus, Rh, Urgency, db_enum


class BloodRequest(Base):
    __tablename__ = "blood_request"
    __table_args__ = (CheckConstraint("units_needed BETWEEN 1 AND 20", name="request_units_range"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"), index=True)
    abo: Mapped[Abo] = mapped_column(db_enum(Abo, "abo_group"))
    rh: Mapped[Rh] = mapped_column(db_enum(Rh, "rh_factor"))
    component: Mapped[Component] = mapped_column(db_enum(Component, "component"))
    units_needed: Mapped[int] = mapped_column(Integer)
    units_secured: Mapped[int] = mapped_column(Integer, default=0)
    urgency: Mapped[Urgency] = mapped_column(db_enum(Urgency, "urgency"))
    needed_by: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[RequestStatus] = mapped_column(db_enum(RequestStatus, "request_status"), default=RequestStatus.submitted, index=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    # Added (decision 0005): low-stock appeals reuse requests; matching state lives on the request.
    kind: Mapped[str] = mapped_column(String, default="patient")  # patient | appeal
    stock_units: Mapped[int] = mapped_column(Integer, default=0)  # reserved locally + proposed transfers
    shortfall: Mapped[int] = mapped_column(Integer, default=0)  # units sought from donors
    wave: Mapped[int] = mapped_column(Integer, default=0)
    next_wave_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    escalated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    @property
    def ref(self) -> str:
        return ("AP-" if self.kind == "appeal" else "RQ-") + self.id.hex[:6].upper()
