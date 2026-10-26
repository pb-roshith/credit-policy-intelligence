"""Consistent, sanitized HTTP responses for infrastructure and unexpected errors."""

from __future__ import annotations

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import DataError, IntegrityError, OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.error_catalog import error_response, resolve_http_error_code


logger = logging.getLogger(__name__)


def install_exception_handlers(app: FastAPI) -> None:
    """Register specific handlers before the final unexpected-error boundary."""

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        logger.info("Request validation failed for %s %s", request.method, request.url.path)
        return error_response(request, "REQ-001")

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        code = resolve_http_error_code(exc.status_code, exc.detail)
        return error_response(
            request,
            code,
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(IntegrityError)
    async def database_integrity_error_handler(request: Request, exc: IntegrityError):
        logger.warning("Database integrity conflict for %s %s", request.method, request.url.path)
        return error_response(request, "DB-001")

    @app.exception_handler(DataError)
    async def database_data_error_handler(request: Request, exc: DataError):
        logger.warning("Invalid database value for %s %s", request.method, request.url.path)
        return error_response(request, "DB-002")

    @app.exception_handler(OperationalError)
    async def database_operational_error_handler(request: Request, exc: OperationalError):
        logger.error("Database unavailable for %s %s", request.method, request.url.path)
        return error_response(request, "DB-003")

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
        logger.error("Database operation failed for %s %s", request.method, request.url.path)
        return error_response(request, "DB-004")

    @app.exception_handler(httpx.TimeoutException)
    async def upstream_timeout_handler(request: Request, exc: httpx.TimeoutException):
        logger.error("Upstream timeout for %s %s", request.method, request.url.path)
        return error_response(request, "EXT-001")

    @app.exception_handler(httpx.HTTPError)
    async def upstream_http_error_handler(request: Request, exc: httpx.HTTPError):
        logger.error("Upstream HTTP failure for %s %s", request.method, request.url.path)
        return error_response(request, "EXT-002")

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        # This is the last application boundary, not a substitute for specific
        # handling near an operation that is expected to fail.
        logger.exception("Unexpected request failure for %s %s", request.method, request.url.path)
        return error_response(request, "SYS-001")
