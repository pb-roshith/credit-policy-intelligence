import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from app.config import (CORS_ORIGINS, ENABLE_HSTS, MAX_REQUEST_BODY_BYTES,
                        RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)
from app.database import initialize_database
from app.security import write_request_error
from app.routers import auth, compliance, controls, dashboard, decision, exceptions, observability, policies, requests
from app.manufacture_data import credit_requests, exposure_history, policy_controls, policy_pdfs

initialize_database()

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        policy_pdfs.shutdown_policy_workers()


app = FastAPI(title="TCS Credit Policy Intelligence API", version="2.0.0", lifespan=lifespan)
logger = logging.getLogger("credit_policy_intelligence")
GENERIC_ERROR_MESSAGE = "An unexpected error occurred. Please try again later."
INVALID_INPUT_MESSAGE = "Please check the information you entered and try again."
_request_times: dict[str, deque[float]] = defaultdict(deque)
_rate_limit_lock = threading.Lock()


def audit_error(request: Request, status_code: int, error_code: str, details: str) -> None:
    try:
        write_request_error(request, status_code, error_code, details)
    except Exception:
        # Audit storage must never replace the original safe response.
        logger.exception("Could not persist an audit error for %s %s", request.method, request.url.path)


@app.exception_handler(RequestValidationError)
async def safe_validation_exception_handler(request: Request, error: RequestValidationError):
    # Keep Pydantic field names, constraints, regexes, and submitted values out
    # of both user-facing responses and audit records.
    logger.warning("Invalid request for %s %s (%s validation error(s))", request.method, request.url.path, len(error.errors()))
    audit_error(
        request, 422, "REQUEST_VALIDATION_FAILED",
        f"{request.method} request validation failed ({len(error.errors())} error(s))",
    )
    return JSONResponse(status_code=422, content={"detail": INVALID_INPUT_MESSAGE})


@app.exception_handler(HTTPException)
async def safe_http_exception_handler(request: Request, error: HTTPException):
    audit_error(
        request, error.status_code, f"HTTP_{error.status_code}",
        f"{request.method} request failed with HTTP status {error.status_code}",
    )
    if error.status_code >= 500:
        logger.error("Server request failed with status %s", error.status_code, exc_info=error)
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": GENERIC_ERROR_MESSAGE},
            headers=error.headers,
        )
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail},
        headers=error.headers,
    )


@app.exception_handler(Exception)
async def safe_unhandled_exception_handler(request: Request, error: Exception):
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path, exc_info=error)
    audit_error(request, 500, "UNHANDLED_SERVER_ERROR", f"{request.method} request failed unexpectedly")
    return JSONResponse(status_code=500, content={"detail": GENERIC_ERROR_MESSAGE})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _rate_limit_lock:
        if len(_request_times) >= 10_000:
            stale_clients = [
                key for key, timestamps in _request_times.items()
                if not timestamps or timestamps[-1] <= now - RATE_LIMIT_WINDOW_SECONDS
            ]
            for key in stale_clients:
                _request_times.pop(key, None)
            if len(_request_times) >= 10_000 and client not in _request_times:
                _request_times.pop(next(iter(_request_times)))
        history = _request_times[client]
        cutoff = now - RATE_LIMIT_WINDOW_SECONDS
        while history and history[0] <= cutoff:
            history.popleft()
        limited = len(history) >= RATE_LIMIT_REQUESTS
        if not limited:
            history.append(now)

    if limited:
        audit_error(request, 429, "RATE_LIMIT_EXCEEDED", f"{request.method} request exceeded the rate limit")
        response = JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please wait and try again."},
            headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
        )
    else:
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_REQUEST_BODY_BYTES:
            audit_error(request, 413, "REQUEST_TOO_LARGE", f"{request.method} request exceeded the size limit")
            response = JSONResponse(status_code=413, content={"detail": "The request is too large."})
        elif request.method in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_REQUEST_BODY_BYTES:
                    break
            if len(body) > MAX_REQUEST_BODY_BYTES:
                audit_error(request, 413, "REQUEST_TOO_LARGE", f"{request.method} request exceeded the size limit")
                response = JSONResponse(status_code=413, content={"detail": "The request is too large."})
            else:
                request._body = bytes(body)
                response = await call_next(request)
        else:
            response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
        "form-action 'none'; object-src 'none'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    if ENABLE_HSTS:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

for router in (
    auth.router,
    requests.router,
    dashboard.router,
    compliance.router,
    credit_requests.router,
    exposure_history.router,
    policy_controls.router,
    policy_pdfs.router,
    controls.router,
    exceptions.router,
    policies.router,
    decision.router,
    observability.router,
):
    app.include_router(router)
