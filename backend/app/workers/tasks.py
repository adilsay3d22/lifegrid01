"""Thin task wrappers around services. Each opens its own session."""

import uuid
from datetime import timedelta

import app.models  # noqa: F401  (register all tables)
from app.core.clock import now
from app.core.db import SessionLocal
from app.modules.admin import service as settings
from app.modules.donors import service as donors
from app.modules.forecasting import service as forecasting
from app.modules.inventory import service as inventory
from app.modules.matching import service as matching
from app.modules.redistribution import service as redistribution
from app.modules.requests import service as requests
from app.workers.celery_app import celery


@celery.task(name="lifegrid.expire_units")
def expire_units() -> int:
    with SessionLocal() as db:
        n = inventory.expire_overdue(db)
        return n + inventory.release_stale_reservations(db, int(settings.get(db, "reservation_timeout_hours")))


@celery.task(name="lifegrid.run_forecasts")
def run_forecasts() -> str:
    with SessionLocal() as db:
        forecasting.aggregate_usage(db, (now() - timedelta(days=1)).date())
        return str(forecasting.run(db))


@celery.task(name="lifegrid.run_plan")
def run_plan(actor: str | None = None) -> str:
    with SessionLocal() as db:
        return str(redistribution.run_plan(db, uuid.UUID(actor) if actor else None).id)


@celery.task(name="lifegrid.advance_matching")
def advance_matching() -> int:
    with SessionLocal() as db:
        return matching.advance(db) + requests.close_overdue(db)


@celery.task(name="lifegrid.remind_eligible")
def remind_eligible() -> int:
    with SessionLocal() as db:
        return donors.remind_eligible(db)
