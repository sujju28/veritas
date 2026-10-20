"""Structured JSON errors. Response bodies omit stack traces and local paths."""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


_STATUS_CODES = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
}


def correlation_id_from(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    if isinstance(value, str) and value:
        return value
    return "unknown"


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    correlation_id: str,
    details: list[dict[str, object]] | None = None,
) -> JSONResponse:
    error: dict[str, object] = {
        "code": code,
        "message": message,
        "correlation_id": correlation_id,
    }
    if details is not None:
        error["details"] = details
    response = JSONResponse(status_code=status_code, content={"error": error})
    response.headers["X-Request-ID"] = correlation_id
    return response


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        correlation_id=correlation_id_from(request),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    return error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        correlation_id=correlation_id_from(request),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
        for item in exc.errors()
    ]
    return error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        correlation_id=correlation_id_from(request),
        details=details,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    del exc
    return error_response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="Internal server error",
        correlation_id=correlation_id_from(request),
    )
