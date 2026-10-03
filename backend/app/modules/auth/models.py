import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.db import Base, UTCDateTime
from app.core.enums import Role, db_enum


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = (CheckConstraint("email IS NOT NULL OR phone_hash IS NOT NULL", name="user_has_login"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    role: Mapped[Role] = mapped_column(db_enum(Role, "user_role"))
    email: Mapped[str | None] = mapped_column(String, unique=True)  # stored lower-cased (citext in spec)
    password_hash: Mapped[str | None]
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    phone_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    phone_hash: Mapped[str | None] = mapped_column(String, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    sites: Mapped[list["UserSite"]] = relationship(cascade="all, delete-orphan", lazy="selectin")

    @property
    def site_ids(self) -> list[uuid.UUID]:
        return [s.site_id for s in self.sites]


class UserSite(Base):
    __tablename__ = "user_site"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), primary_key=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"), primary_key=True)


class RefreshToken(Base):
    __tablename__ = "refresh_token"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class OtpChallenge(Base):
    __tablename__ = "otp_challenge"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    phone_hash: Mapped[str] = mapped_column(String, index=True)
    code_hash: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)  # added: per-hour request limit (SEC-03)
