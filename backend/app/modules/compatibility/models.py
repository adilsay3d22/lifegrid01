from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.enums import Abo, Component, Rh, db_enum


class CompatRule(Base):
    __tablename__ = "compat_rule"
    component: Mapped[Component] = mapped_column(db_enum(Component, "component"), primary_key=True)
    recipient_abo: Mapped[Abo] = mapped_column(db_enum(Abo, "abo_group"), primary_key=True)
    recipient_rh: Mapped[Rh] = mapped_column(db_enum(Rh, "rh_factor"), primary_key=True)
    donor_abo: Mapped[Abo] = mapped_column(db_enum(Abo, "abo_group"), primary_key=True)
    donor_rh: Mapped[Rh] = mapped_column(db_enum(Rh, "rh_factor"), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer)
