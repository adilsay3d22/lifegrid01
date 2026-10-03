"""Usage aggregation and nightly forecasts (FR-FC-01..04). Algorithms live in engine.py (pure)."""

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import GROUPS, Abo, Component, Rh, SiteType, UnitStatus
from app.modules.forecasting import engine
from app.modules.forecasting.models import Forecast, UsageDaily
from app.modules.inventory.models import BloodUnit, UnitMovement
from app.modules.sites.models import Site

HISTORY_DAYS = 365
HORIZON = 7


def series_groups(c: Component) -> list[tuple[Abo, Rh]]:
    """8 groups for red cells and platelets; 4 ABO groups for plasma, stored under Rh.pos (spec 13.1)."""
    return [(a, Rh.pos) for a in Abo] if c is Component.plasma else list(GROUPS)


def local_today(site: Site) -> date:
    return now().astimezone(ZoneInfo(site.timezone)).date()


def aggregate_usage(db: Session, day: date) -> int:
    """usage_daily for `day` = units issued that day, per site, component and group (FR-FC-01)."""
    rows = 0
    for site in db.scalars(select(Site)):
        tz = ZoneInfo(site.timezone)
        start = datetime.combine(day, time.min, tz)
        end = start + timedelta(days=1)
        q = (select(BloodUnit.component, BloodUnit.abo, BloodUnit.rh, func.count())
             .join(UnitMovement, UnitMovement.unit_id == BloodUnit.id)
             .where(UnitMovement.to_status == UnitStatus.issued, UnitMovement.to_site_id == site.id,
                    UnitMovement.created_at >= start, UnitMovement.created_at < end)
             .group_by(BloodUnit.component, BloodUnit.abo, BloodUnit.rh))
        counts: dict[tuple[Component, Abo, Rh], int] = defaultdict(int)
        for c, a, r, n in db.execute(q):
            counts[(c, a, Rh.pos if c is Component.plasma else r)] += n
        db.execute(delete(UsageDaily).where(UsageDaily.site_id == site.id, UsageDaily.day == day))
        for (c, a, r), n in counts.items():
            db.add(UsageDaily(site_id=site.id, day=day, component=c, abo=a, rh=r, units_used=n))
            rows += 1
    db.commit()
    return rows


def history(db: Session, site_id: uuid.UUID, c: Component, abo: Abo, rh: Rh, end: date, days: int) -> np.ndarray:
    """Daily usage for the `days` days ending the day before `end`; missing days count as zero (spec 13.1)."""
    start = end - timedelta(days=days)
    y = np.zeros(days)
    for d, n in db.execute(select(UsageDaily.day, UsageDaily.units_used).where(
            UsageDaily.site_id == site_id, UsageDaily.component == c, UsageDaily.abo == abo, UsageDaily.rh == rh,
            UsageDaily.day >= start, UsageDaily.day < end)):
        y[(d - start).days] = n
    return y


def run(db: Session, models: list[str] | None = None) -> uuid.UUID:
    """Nightly job (01:30): 7-day forecast per hospital series with point, p10 and p90, model and error stored."""
    run_id = uuid.uuid4()
    for site in db.scalars(select(Site).where(Site.active, Site.type == SiteType.hospital)):
        today = local_today(site)
        first = db.scalar(select(func.min(UsageDaily.day)).where(UsageDaily.site_id == site.id))
        if first is None:
            continue
        n = min(HISTORY_DAYS, (today - first).days)
        for c in Component:
            for a, r in series_groups(c):
                y = history(db, site.id, c, a, r, today, n)
                if not y.any():
                    continue
                res = engine.forecast(y, HORIZON, models)
                for k in range(HORIZON):
                    db.add(Forecast(run_id=run_id, site_id=site.id, day=today + timedelta(days=k), component=c, abo=a, rh=r,
                                    point=round(float(res.point[k]), 2), low=round(float(res.low[k]), 2), high=round(float(res.high[k]), 2),
                                    model=res.model, model_version=engine.MODEL_VERSION, backtest_mae=round(res.backtest_mae, 3),
                                    baseline_mae=round(res.baseline_mae, 3)))
    db.commit()
    return run_id


def latest(db: Session, site_id: uuid.UUID, c: Component, abo: Abo, rh: Rh) -> list[Forecast]:
    run_id = db.scalar(select(Forecast.run_id).where(Forecast.site_id == site_id, Forecast.component == c, Forecast.abo == abo,
                                                     Forecast.rh == rh).order_by(Forecast.created_at.desc(), Forecast.id.desc()).limit(1))
    if run_id is None:
        return []
    return list(db.scalars(select(Forecast).where(Forecast.run_id == run_id, Forecast.site_id == site_id, Forecast.component == c,
                                                  Forecast.abo == abo, Forecast.rh == rh).order_by(Forecast.day)))


def accuracy(db: Session, site_id: uuid.UUID | None, c: Component | None, days: int = 28) -> dict[str, float | int]:
    """MAE and p10–p90 coverage over the last `days` days (FR-FC-04). Each day is scored with the most recent forecast
    issued before that day; only days with a forecast count."""
    end = date.fromordinal(now().date().toordinal())
    start = end - timedelta(days=days)
    q = select(Forecast).where(Forecast.day >= start, Forecast.day < end)
    if site_id:
        q = q.where(Forecast.site_id == site_id)
    if c:
        q = q.where(Forecast.component == c)
    best: dict[tuple[Any, ...], Forecast] = {}
    for f in db.scalars(q):
        k = (f.site_id, f.day, f.component, f.abo, f.rh)
        if f.created_at.date() <= f.day and (k not in best or f.created_at > best[k].created_at):
            best[k] = f
    actual = {(u.site_id, u.day, u.component, u.abo, u.rh): u.units_used
              for u in db.scalars(select(UsageDaily).where(UsageDaily.day >= start, UsageDaily.day < end))}
    errs, inside = [], 0
    for key, f in best.items():
        y = actual.get(key, 0)
        errs.append(abs(float(f.point) - y))
        inside += float(f.low) <= y <= float(f.high)
    return {"days": days, "scored": len(errs), "mae": round(float(np.mean(errs)), 3) if errs else 0.0,
            "coverage": round(inside / len(errs), 3) if errs else 0.0}
