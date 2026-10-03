"""Demand forecasting as pure functions (spec section 13.1). No database; the service and simulator both call this.

Models, simplest first: seasonal naive (baseline), Poisson (sparse series), exponential smoothing with additive weekly
seasonality. Selection: lowest mean absolute error on a rolling-origin backtest over the last 28 days; ties keep the
simpler model. Gradient boosting is deferred (decision 0003).
"""

import warnings
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.stats import poisson as _poisson

MODEL_VERSION = "2026.10.1"
WEEK = 7
SPARSE_MEAN = 0.5  # 28-day mean below this -> sparse series
MIN_ETS_HISTORY = 8 * WEEK
BACKTEST_DAYS = 28


@dataclass
class Band:
    point: np.ndarray
    low: np.ndarray
    high: np.ndarray


@dataclass
class Result(Band):
    model: str
    backtest_mae: float
    baseline_mae: float


def _band(point: np.ndarray, resid: np.ndarray) -> Band:
    point = np.clip(point, 0, None)
    if resid.size >= 5:
        q10, q90 = np.quantile(resid, [0.1, 0.9])
    else:
        q10, q90 = -np.sqrt(point.mean() + 1e-9), np.sqrt(point.mean() + 1e-9)
    low = np.clip(point + min(q10, 0), 0, None)
    high = np.clip(point + max(q90, 0), 0, None)
    return Band(point, np.minimum(low, point), np.maximum(high, point))


def seasonal_naive(y: np.ndarray, h: int) -> Band:
    """Same weekday last week; interval from this model's errors over the last 8 weeks."""
    if y.size < WEEK:
        return _band(np.full(h, y.mean() if y.size else 0.0), np.array([]))
    point = np.array([y[-WEEK + (k % WEEK)] for k in range(h)], dtype=float)
    hist = y[-(8 * WEEK + WEEK):]
    resid = hist[WEEK:] - hist[:-WEEK]
    return _band(point, resid)


def poisson(y: np.ndarray, h: int) -> Band:
    """Mean of the last 28 days; band = Poisson 10th/90th percentiles."""
    mu = float(y[-BACKTEST_DAYS:].mean()) if y.size else 0.0
    point = np.full(h, mu)
    return Band(point, np.full(h, float(_poisson.ppf(0.1, mu)) if mu > 0 else 0.0), np.full(h, float(_poisson.ppf(0.9, mu)) if mu > 0 else 0.0))


def ets(y: np.ndarray, h: int, fast: bool = False) -> Band:
    """Holt-Winters, additive weekly seasonality. `fast` fixes smoothing constants (simulator speed; decision 0003)."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = ExponentialSmoothing(y.astype(float), trend=None, seasonal="add", seasonal_periods=WEEK,
                                 initialization_method="heuristic" if fast else "estimated")
        fit = m.fit(smoothing_level=0.15, smoothing_seasonal=0.05, optimized=False) if fast else m.fit()
    resid = (y - fit.fittedvalues)[-8 * WEEK:]
    return _band(np.asarray(fit.forecast(h)), resid)


MODELS: dict[str, Callable[[np.ndarray, int], Band]] = {
    "seasonal_naive": seasonal_naive,
    "poisson": poisson,
    "ets": ets,
    "ets_fast": lambda y, h: ets(y, h, fast=True),
}
COMPLEXITY = ["seasonal_naive", "poisson", "ets_fast", "ets"]


def eligible(y: np.ndarray, allowed: list[str]) -> list[str]:
    sparse = y[-BACKTEST_DAYS:].mean() < SPARSE_MEAN if y.size else True
    out = ["seasonal_naive"]
    if sparse and "poisson" in allowed:
        out.append("poisson")
    if not sparse and y.size >= MIN_ETS_HISTORY + BACKTEST_DAYS:
        out += [m for m in ("ets_fast", "ets") if m in allowed]
    return out


def backtest_mae(y: np.ndarray, model: str, step: int = WEEK) -> float:
    """Rolling origin over the last 28 days, re-fitting every `step` days and scoring the next `step` days."""
    errs = []
    for origin in range(y.size - BACKTEST_DAYS, y.size, step):
        if origin < WEEK:
            continue
        f = MODELS[model](y[:origin], step)
        actual = y[origin:origin + step]
        errs.append(np.abs(f.point[: actual.size] - actual))
    return float(np.concatenate(errs).mean()) if errs else float("inf")


def forecast(y: np.ndarray, h: int = WEEK, allowed: list[str] | None = None) -> Result:
    """Pick the best eligible model for one series and forecast h days. Missing days must already be zeros."""
    y = np.asarray(y, dtype=float)
    allowed = allowed or ["seasonal_naive", "poisson", "ets"]
    cands = eligible(y, allowed)
    scores = {m: backtest_mae(y, m) for m in cands}
    best = min(cands, key=lambda m: (round(scores[m], 9), COMPLEXITY.index(m)))
    b = MODELS[best](y, h)
    point = np.clip(b.point, 0, None)  # spec 13.1: clip negatives, enforce low <= point <= high
    return Result(point, np.minimum(np.clip(b.low, 0, None), point), np.maximum(b.high, point), model=best,
                  backtest_mae=scores[best], baseline_mae=scores["seasonal_naive"])
