"""In-app and SMS notifications through the provider adapter (spec section 8). Payloads never carry contact details."""

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core import sms
from app.core.config import get_settings
from app.core.security import decrypt
from app.modules.auth.models import AppUser
from app.modules.notifications.models import Notification

log = logging.getLogger("lifegrid.notify")

# FR-MAT-03: invitations show only the group needed, the hospital area and urgency.
TEMPLATES = {
    "invite": "LifeGrid: {urgency} need for {group} blood near {area}. Open the LifeGrid app to accept or decline.",
    "appeal": "LifeGrid: {area} is running low on {group} blood. If you can donate, open the LifeGrid app to accept.",
    "donor_accepted": "LifeGrid: a donor accepted your request {ref}. Open the app to message them.",
    "request_update": "LifeGrid: your request {ref} is now {status}.",
    "eligible_again": "LifeGrid: you can donate blood again from today. Thank you for staying available.",
    "escalation": "LifeGrid: request {ref} at {area} has no accepted donors after {waves} waves.",
}


def notify(db: Session, user_id: uuid.UUID, template: str, payload: dict[str, Any], sms_too: bool = True) -> None:
    """Write an in-app notification and, if the user has a phone, send the SMS. Failures are recorded, not raised."""
    db.add(Notification(user_id=user_id, channel="in_app", template=template, payload=payload, status="unread"))
    if not sms_too:
        return
    user = db.get(AppUser, user_id)
    if not user or not user.phone_enc:
        return
    text = TEMPLATES[template].format(**payload)
    try:
        sms.send(decrypt(user.phone_enc, get_settings().phone_enc_key), text)
        db.add(Notification(user_id=user_id, channel="sms", template=template, payload=payload, status="sent"))
    except Exception as e:  # provider down must not block matching
        log.warning("sms failed: %s", type(e).__name__)
        db.add(Notification(user_id=user_id, channel="sms", template=template, payload=payload, status="failed", error=type(e).__name__))
