"""Centralised exception classes and FastAPI exception handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, NoResultFound


# ---------------------------------------------------------------------------
# Application exception
# ---------------------------------------------------------------------------


class AppException(Exception):
    """Base application exception returned as structured JSON."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        field: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        super().__init__(message)


# ---------------------------------------------------------------------------
# Convenience subclasses
# ---------------------------------------------------------------------------


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found.", field: str | None = None) -> None:
        super().__init__(code="NOT_FOUND", message=message, status_code=404, field=field)


class ConflictException(AppException):
    def __init__(self, message: str = "Resource conflict.", field: str | None = None) -> None:
        super().__init__(code="CONFLICT", message=message, status_code=409, field=field)


class ForbiddenException(AppException):
    def __init__(self, message: str = "Forbidden.", field: str | None = None) -> None:
        super().__init__(code="FORBIDDEN", message=message, status_code=403, field=field)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Not authenticated.", field: str | None = None) -> None:
        super().__init__(code="UNAUTHORIZED", message=message, status_code=401, field=field)


# ---------------------------------------------------------------------------
# Error response helper
# ---------------------------------------------------------------------------


def _error_response(
    status_code: int,
    code: str,
    message: str,
    field: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "field": field}},
    )


# ---------------------------------------------------------------------------
# FastAPI exception handler registration
# ---------------------------------------------------------------------------


def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the FastAPI app."""

    @app.exception_handler(AppException)
    async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.field)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        if errors:
            first = errors[0]
            field = ".".join(str(loc) for loc in first.get("loc", []) if loc != "body")
            message = first.get("msg", "Validation error.")
        else:
            field = None
            message = "Validation error."
        return _error_response(422, "VALIDATION_ERROR", message, field or None)

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_request: Request, _exc: IntegrityError) -> JSONResponse:
        return _error_response(409, "CONFLICT", "A resource with the given values already exists.")

    @app.exception_handler(NoResultFound)
    async def no_result_handler(_request: Request, _exc: NoResultFound) -> JSONResponse:
        return _error_response(404, "NOT_FOUND", "Resource not found.")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")
