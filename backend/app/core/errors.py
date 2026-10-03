"""RFC 9457 problem details with stable `code` values (spec section 12)."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

TITLES = {400: "Bad request", 401: "Unauthenticated", 403: "Forbidden", 404: "Not found", 409: "Conflict",
          422: "Validation failed", 429: "Too many requests", 500: "Internal error", 503: "Unavailable"}


class Problem(Exception):
    def __init__(self, status: int, code: str, detail: str = "", **extra: Any) -> None:
        super().__init__(detail or code)
        self.status, self.code, self.detail, self.extra = status, code, detail or code, extra


def _body(status: int, code: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"type": f"https://lifegrid.example/problems/{code}", "title": TITLES.get(status, "Error"),
            "status": status, "detail": detail, "code": code, **extra}


def problem_response(status: int, code: str, detail: str, **extra: Any) -> JSONResponse:
    return JSONResponse(_body(status, code, detail, **extra), status_code=status, media_type="application/problem+json")


def install(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def _problem(_: Request, e: Problem) -> JSONResponse:
        return problem_response(e.status, e.code, e.detail, **e.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()]
        return problem_response(422, "validation_error", "Request body or parameters are invalid.", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException) -> JSONResponse:
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(e.status_code, "error")
        return problem_response(e.status_code, code, str(e.detail))
