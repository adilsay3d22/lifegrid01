import uuid
from datetime import datetime
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.core.enums import Abo, Component, Rh, UnitStatus


class UnitIn(BaseModel):
    """FR-INV-01: every field required; expiry must be after collection."""

    unit_code: str = Field(pattern=r"^[A-Z0-9-]{6,24}$")
    abo: Abo
    rh: Rh
    component: Component
    collected_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def _expiry_after_collection(self) -> Self:
        if self.expires_at <= self.collected_at:
            raise ValueError("expiry_before_collection")
        return self


class ReceiveIn(UnitIn):
    site_id: uuid.UUID


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    unit_code: str
    abo: Abo
    rh: Rh
    component: Component
    collected_at: datetime
    expires_at: datetime
    site_id: uuid.UUID
    status: UnitStatus
    reserved_for: uuid.UUID | None


class UnitPage(BaseModel):
    items: list[UnitOut]
    next_cursor: str | None
    total: int


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    from_status: UnitStatus | None
    to_status: UnitStatus
    from_site_id: uuid.UUID | None
    to_site_id: uuid.UUID | None
    transfer_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    actor: str = "system"  # staff email, or "system" for scheduled jobs
    reason: str
    created_at: datetime


class UnitDetail(BaseModel):
    unit: UnitOut
    movements: list[MovementOut]


class TransitionIn(BaseModel):
    action: str = Field(pattern=r"^(issue|quarantine|clear|discard)$")
    reason: str = Field(default="", max_length=500)


class BulkTransitionIn(TransitionIn):
    unit_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class TransitionOut(BaseModel):
    changed: int


class ImportOut(BaseModel):
    imported: int
    errors: list[dict[str, object]]


class ExcursionIn(BaseModel):
    site_id: uuid.UUID | None = None
    transfer_id: uuid.UUID | None = None
    component: Component
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    min_c: float | None = Field(default=None, ge=-80, le=80)
    max_c: float | None = Field(default=None, ge=-80, le=80)

    @model_validator(mode="after")
    def _where(self) -> Self:
        if (self.site_id is None) == (self.transfer_id is None):
            raise ValueError("give exactly one of site_id or transfer_id")
        return self


class ExcursionOut(BaseModel):
    id: uuid.UUID
    quarantined: int


class StockCell(BaseModel):
    site_id: uuid.UUID
    component: Component
    abo: Abo
    rh: Rh
    band_0_2: int
    band_3_7: int
    band_8: int
