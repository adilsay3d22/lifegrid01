"""FastAPI app factory. All endpoints live under /api/v1 (spec section 12)."""

import asyncio
import logging as pylogging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core import errors, logging
from app.core.config import get_settings
from app.core.db import engine

API = "/api/v1"


class SecurityHeaders(BaseHTTPMiddleware):
    """SEC-12: CSP, HSTS, frame denial. The API serves JSON only, so the CSP is locked down."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        resp = await call_next(request)
        resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp


_due = {"match": 0.0, "expire": 0.0}
SERVERLESS = bool(os.environ.get("VERCEL"))  # set by Vercel; no long-lived process there


def _run_due_jobs() -> None:
    """Without Celery beat (no Docker, or serverless), run the short-interval jobs from the API process."""
    from app.workers import tasks

    t = time.monotonic()
    try:
        if t >= _due["match"]:
            _due["match"] = t + 60
            tasks.advance_matching()
        if t >= _due["expire"]:
            _due["expire"] = t + 900
            tasks.expire_units()
    except Exception:
        pylogging.getLogger("lifegrid.jobs").exception("in-process job failed")


async def _dev_scheduler() -> None:
    while True:
        await asyncio.sleep(60)
        await asyncio.to_thread(_run_due_jobs)


class RequestTick(BaseHTTPMiddleware):
    """Serverless: no background loop, so due jobs run (at most once a minute) before a request is handled."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if time.monotonic() >= _due["match"]:
            await asyncio.to_thread(_run_due_jobs)
        return await call_next(request)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    loop = s.env in ("dev", "demo") and s.celery_always_eager and not SERVERLESS
    task = asyncio.create_task(_dev_scheduler()) if loop else None
    yield
    if task:
        task.cancel()


def create_app() -> FastAPI:
    s = get_settings()
    logging.setup(s.log_level)
    app = FastAPI(title="LifeGrid API", version="0.1.0", openapi_url=f"{API}/openapi.json", docs_url=f"{API}/docs", redoc_url=None,
                  lifespan=lifespan)
    errors.install(app)
    app.add_middleware(SecurityHeaders)
    app.add_middleware(CORSMiddleware, allow_origins=[s.app_origin], allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])
    if SERVERLESS and s.env in ("dev", "demo") and s.celery_always_eager:
        app.add_middleware(RequestTick)
    app.add_middleware(logging.RequestIdMiddleware)

    from app.modules.admin.router import router as admin
    from app.modules.audit.router import router as audit
    from app.modules.auth.router import router as auth
    from app.modules.compatibility.router import router as compatibility
    from app.modules.donors.router import router as donors
    from app.modules.forecasting.router import router as forecasting
    from app.modules.inventory.router import router as inventory
    from app.modules.matching.router import router as matching
    from app.modules.redistribution.router import router as redistribution
    from app.modules.requests.router import router as requests
    from app.modules.sites.router import router as sites

    api = APIRouter(prefix=API)
    for r in (auth, sites, admin, audit, inventory, compatibility, forecasting, redistribution, requests, donors, matching):
        api.include_router(r)

    @api.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/readyz", tags=["ops"], response_model=None)
    def readyz() -> dict[str, str] | JSONResponse:
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "db_unavailable"}, status_code=503)
        return {"status": "ready"}

    app.include_router(api)
    modules = (auth, sites, admin, audit, inventory, compatibility, forecasting, redistribution, requests, donors, matching)
    app.state.api_routes = [r for rt in (*modules, api) for r in rt.routes]
    return app


app = create_app()
