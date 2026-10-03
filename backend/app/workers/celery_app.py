"""Celery app and beat schedule (spec section 8). Workers share the service layer and database; they never call the API."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

s = get_settings()
celery = Celery("lifegrid", broker=s.redis_url, backend=s.redis_url, include=["app.workers.tasks"])
celery.conf.update(
    task_always_eager=s.celery_always_eager,
    task_eager_propagates=True,
    timezone="Asia/Dhaka",  # plan_run_time / forecast_run_time are local times (spec section 19)
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "expire-and-release": {"task": "lifegrid.expire_units", "schedule": crontab(minute="*/15")},  # FR-INV-04
        "nightly-forecast": {"task": "lifegrid.run_forecasts", "schedule": crontab(hour=1, minute=30)},  # FR-FC-02
        "nightly-plan": {"task": "lifegrid.run_plan", "schedule": crontab(hour=2, minute=0)},  # FR-RD-01
        "matching-waves": {"task": "lifegrid.advance_matching", "schedule": 60.0},  # FR-MAT-02, request closing
        "eligibility-reminders": {"task": "lifegrid.remind_eligible", "schedule": crontab(hour=9, minute=0)},  # FR-DON-04
    },
)
