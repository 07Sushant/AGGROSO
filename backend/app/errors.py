"""Error envelope: ``{"error": {"code", "message", "details", "request_id"}}`` everywhere."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging import get_logger

log = get_logger("app")

# Stable code -> HTTP status mapping (spec §9).
STATUS_BY_CODE: dict[str, int] = {
    "VALIDATION_ERROR": 422,
    "LIMIT_EXCEEDED": 422,
    "UNAUTHENTICATED": 401,
    "FORBIDDEN": 403,
    "APPROVAL_REQUIRED": 403,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "INVALID_STATE": 409,
    "DRIFT_DETECTED": 409,
    "IDEMPOTENCY_KEY_REUSED": 409,
    "RATE_LIMITED": 429,
    "LLM_UNAVAILABLE": 503,
    "LLM_TIMEOUT": 504,
    "INTERNAL": 500,
}


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code or STATUS_BY_CODE.get(code, 400)
        self.headers = headers


def _request_id(request: Request) -> str | None:
    return request.scope.get("state", {}).get("request_id")


def error_body(
    code: str, message: str, request_id: str | None, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }


def internal_error_response(request_id: str | None) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL", "An unexpected error occurred.", request_id),
    )


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    log.info("request.error", code=exc.code, status=exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, _request_id(request), exc.details),
        headers=exc.headers,
    )


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {
            "path": ".".join(str(p) for p in err.get("loc", ())),
            "code": err.get("type", "invalid"),
            "message": err.get("msg", "Invalid value"),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_body(
            "VALIDATION_ERROR",
            "Request validation failed.",
            _request_id(request),
            {"errors": errors},
        ),
    )


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        code, message = "NOT_FOUND", "Resource not found."
    elif exc.status_code == 405:
        code, message = "METHOD_NOT_ALLOWED", "Method not allowed."
    elif exc.status_code == 401:
        code, message = "UNAUTHENTICATED", "Authentication required."
    elif exc.status_code == 403:
        code, message = "FORBIDDEN", "Not allowed."
    elif exc.status_code >= 500:
        code, message = "INTERNAL", "An unexpected error occurred."
    else:
        code, message = "VALIDATION_ERROR", str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message, _request_id(request)),
        headers=getattr(exc, "headers", None),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
