"""Fixed-window rate limits (SEC-10). Redis when reachable; an in-process window otherwise (dev, tests, Redis down)."""

import time
from collections import defaultdict
from typing import Any

from app.core.config import get_settings
from app.core.errors import Problem

_mem: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
_redis: Any = None


def _client() -> Any:
    global _redis
    if _redis is None:
        try:
            import redis

            r = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.2, socket_timeout=0.2)
            r.ping()
            _redis = r
        except Exception:
            _redis = False
    return _redis or None


def hit(key: str, limit: int, window_s: int) -> None:
    r = _client()
    if r is not None:
        try:
            n = r.incr(f"rl:{key}")
            if n == 1:
                r.expire(f"rl:{key}", window_s)
            if n > limit:
                raise Problem(429, "rate_limited", "Too many attempts. Wait and try again.")
            return
        except Problem:
            raise
        except Exception:
            pass  # Redis hiccup: fall through to memory so sign-in keeps working (NFR-07)
    count, start = _mem[key]
    t = time.monotonic()
    if t - start > window_s:
        count, start = 0, t
    count += 1
    _mem[key] = (count, start)
    if count > limit:
        raise Problem(429, "rate_limited", "Too many attempts. Wait and try again.")


def reset() -> None:
    _mem.clear()
