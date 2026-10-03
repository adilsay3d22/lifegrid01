import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.db import get_db
from app.core.deps import Principal, require
from app.core.enums import Abo, MatchStatus, Rh, Role, Urgency
from app.core.errors import Problem
from app.modules.matching import service
from app.modules.matching.models import DonorMatch
from app.modules.requests.models import BloodRequest

router = APIRouter(tags=["matching"])
donor = require(Role.donor)
chatters = require(Role.donor, Role.requester, Role.hospital_lead, Role.bank_manager, Role.donor_coordinator)


class InvitationOut(BaseModel):
    id: uuid.UUID
    request_ref: str
    abo: Abo
    rh: Rh
    hospital_area: str
    urgency: Urgency
    needed_by: datetime
    status: MatchStatus
    kind: str


class RespondIn(BaseModel):
    accept: bool


class OutcomeIn(BaseModel):
    outcome: MatchStatus


class MessageOut(BaseModel):
    id: int
    mine: bool
    body: str
    created_at: datetime


class ThreadOut(BaseModel):
    id: uuid.UUID
    request_ref: str
    hospital_area: str
    role: str
    donor_shares_phone: bool
    requester_shares_phone: bool
    counterpart_phone: str | None
    messages: list[MessageOut]


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


@router.get("/donor/invitations", response_model=list[InvitationOut])
def invitations(p: Principal = Depends(donor), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return service.invitations(db, p.user_id)


@router.post("/matches/{match_id}/respond", status_code=204)
def respond(match_id: uuid.UUID, body: RespondIn, p: Principal = Depends(donor), db: Session = Depends(get_db)) -> Response:
    service.respond(db, match_id, p.user_id, body.accept)
    return Response(status_code=204)


@router.post("/matches/{match_id}/outcome", status_code=204)
def outcome(match_id: uuid.UUID, body: OutcomeIn, p: Principal = Depends(require(Role.hospital_lead, Role.donor_coordinator)),
            db: Session = Depends(get_db)) -> Response:
    m = db.get(DonorMatch, match_id)
    r = db.get(BloodRequest, m.request_id) if m else None
    if not r:
        raise Problem(404, "not_found", "Match not found.")
    p.require_site(r.site_id)
    service.outcome(db, match_id, body.outcome, p.user_id)
    return Response(status_code=204)


@router.get("/matches/{match_id}/messages", response_model=ThreadOut)
def messages(match_id: uuid.UUID, p: Principal = Depends(chatters), db: Session = Depends(get_db)) -> dict[str, Any]:
    return service.thread(db, match_id, p.user_id)


@router.post("/matches/{match_id}/messages", status_code=204)
def post_message(match_id: uuid.UUID, body: MessageIn, p: Principal = Depends(chatters), db: Session = Depends(get_db)) -> Response:
    ratelimit.hit(f"msg:{p.user_id}", 60, 600)
    service.post_message(db, match_id, p.user_id, body.body)
    return Response(status_code=204)


@router.post("/matches/{match_id}/share-phone", status_code=204)
def share_phone(match_id: uuid.UUID, p: Principal = Depends(chatters), db: Session = Depends(get_db)) -> Response:
    service.share_phone(db, match_id, p.user_id)
    return Response(status_code=204)
