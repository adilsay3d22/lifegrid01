"""SMS provider adapter (spec section 8). Only the mock exists in v1; real providers plug in behind send()."""

import logging

from app.core.config import get_settings

log = logging.getLogger("lifegrid.sms")
outbox: list[tuple[str, str]] = []  # (phone, body) — read by tests and the dev console


def send(phone: str, body: str) -> None:
    provider = get_settings().sms_provider
    if provider != "mock":
        raise NotImplementedError(f"SMS provider {provider!r} is not configured")
    outbox.append((phone, body))
    del outbox[:-200]
    if get_settings().env == "dev":
        log.info("mock SMS sent: %s", body)  # phone is never logged (SEC-14)
