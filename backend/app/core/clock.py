"""Single source of 'now' so time-dependent code and tests share one clock (spec section 17: fixed clock)."""

from collections.abc import Callable
from datetime import UTC, datetime

_now: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731


def now() -> datetime:
    return _now()


def set_clock(fn: Callable[[], datetime] | None) -> None:
    global _now
    _now = fn or (lambda: datetime.now(UTC))
