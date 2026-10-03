import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import STAFF, Principal, require
from app.core.enums import Abo, Component, Rh
from app.core.errors import Problem
from app.modules.forecasting import service
from app.modules.sites.models import Site

router = APIRouter(tags=["forecasting"])


class Point(BaseModel):
    day: date
    actual: float | None = None
    point: float | None = None
    low: float | None = None
    high: float | None = None


class Series(BaseModel):
    model: str | None
    model_version: str | None
    mae: float | None
    baseline_mae: float | None
    coverage: float | None
    points: list[Point]


class Accuracy(BaseModel):
    days: int
    scored: int
    mae: float
    coverage: float


@router.get("/forecasts", response_model=Series)
def get_series(site_id: uuid.UUID, component: Component, abo: Abo, rh: Rh = Rh.pos,
               p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)) -> Series:
    """28 days of actual usage plus the latest 7-day forecast for one series. Plasma is ABO-only (use rh=pos)."""
    p.require_site(site_id)  # hospital leads: own site only (spec section 3)
    site = db.get(Site, site_id)
    if not site:
        raise Problem(404, "not_found", "Site not found.")
    if component is Component.plasma:
        rh = Rh.pos
    today = service.local_today(site)
    hist = service.history(db, site_id, component, abo, rh, today, 28)
    points = [Point(day=today - timedelta(days=28 - i), actual=float(v)) for i, v in enumerate(hist)]
    fc = service.latest(db, site_id, component, abo, rh)
    by_day = {pt.day: pt for pt in points}
    for f in fc:
        pt = by_day.get(f.day) or Point(day=f.day)
        pt.point, pt.low, pt.high = float(f.point), float(f.low), float(f.high)
        if f.day not in by_day:
            points.append(pt)
    acc = service.accuracy(db, site_id, component)
    first = fc[0] if fc else None
    return Series(model=first.model if first else None, model_version=first.model_version if first else None,
                  mae=float(first.backtest_mae) if first else None, baseline_mae=float(first.baseline_mae) if first else None,
                  coverage=acc["coverage"] if acc["scored"] else None, points=points)


@router.get("/forecasts/accuracy", response_model=Accuracy)
def get_accuracy(site_id: uuid.UUID | None = None, component: Component | None = None,
                 p: Principal = Depends(require(*STAFF)), db: Session = Depends(get_db)) -> Accuracy:
    if site_id:
        p.require_site(site_id)
    elif not p.region_wide:
        raise Problem(403, "out_of_scope", "Choose one of your sites.")
    return Accuracy.model_validate(service.accuracy(db, site_id, component))
