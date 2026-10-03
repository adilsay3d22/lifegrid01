"""JSON logs with a request ID (NFR-18); phone numbers and tokens are redacted (SEC-14)."""

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

request_id: ContextVar[str] = ContextVar("request_id", default="-")

_REDACT = [
    (re.compile(r"\+?\d[\d\s-]{7,}\d"), "[phone]"),
    (re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+"), "[token]"),
    (re.compile(r"(?i)(password|token|code|secret)=\S+"), r"\1=[redacted]"),
]


def redact(s: str) -> str:
    for rx, rep in _REDACT:
        s = rx.sub(rep, s)
    return s


class JsonFormatter(logging.Formatter):
    def format(self, r: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(r, "%Y-%m-%dT%H:%M:%S%z"), "level": r.levelname, "logger": r.name,
               "request_id": request_id.get(), "msg": redact(r.getMessage())}
        for k in ("method", "path", "status", "ms"):
            if hasattr(r, k):
                out[k] = getattr(r, k)
        if r.exc_info:
            out["exc"] = redact(self.formatException(r.exc_info))
        return json.dumps(out)


def setup(level: str = "INFO") -> None:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(level)


log = logging.getLogger("lifegrid.http")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id.set(rid)
        t0 = time.perf_counter()
        try:
            resp = await call_next(request)
            resp.headers["x-request-id"] = rid
            log.info("request", extra={"method": request.method, "path": request.url.path, "status": resp.status_code,
                                       "ms": round((time.perf_counter() - t0) * 1000, 1)})
            return resp
        finally:
            request_id.reset(token)
