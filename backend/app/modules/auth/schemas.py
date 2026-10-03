import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import Role


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=512)


class TotpIn(BaseModel):
    challenge: str
    code: str = Field(pattern=r"^\d{6}$")


class OtpRequestIn(BaseModel):
    phone: str = Field(max_length=32)


class OtpVerifyIn(BaseModel):
    phone: str = Field(max_length=32)
    code: str = Field(pattern=r"^\d{6}$")
    role: Literal["donor", "requester"] = "donor"


class Me(BaseModel):
    id: uuid.UUID
    role: Role
    email: str | None
    site_ids: list[uuid.UUID]


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: Me


class LoginOut(BaseModel):
    totp_required: bool
    challenge: str | None = None
    session: TokenOut | None = None
