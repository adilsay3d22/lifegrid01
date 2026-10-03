import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base, BigId, UTCDateTime
from app.core.enums import MatchStatus, db_enum


class DonorMatch(Base):
    __tablename__ = "donor_match"
    __table_args__ = (UniqueConstraint("request_id", "donor_id", name="match_once_per_request"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("blood_request.id"), index=True)
    donor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donor.id"), index=True)
    wave: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Numeric(5, 4))
    status: Mapped[MatchStatus] = mapped_column(db_enum(MatchStatus, "match_status"), default=MatchStatus.invited)
    invited_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    outcome_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class MessageThread(Base):
    __tablename__ = "message_thread"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("donor_match.id"), unique=True)
    donor_shares_phone: Mapped[bool] = mapped_column(Boolean, default=False)
    requester_shares_phone: Mapped[bool] = mapped_column(Boolean, default=False)


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (CheckConstraint("length(body) <= 1000", name="message_length"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("message_thread.id"), index=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    body: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
