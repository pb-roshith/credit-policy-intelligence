"""HTTP safeguards shared by the CPI and Data Manufacturing APIs."""
import logging
import threading
import time
from collections import OrderedDict, defaultdict, deque
from psycopg import Error as DatabaseError, OperationalError
from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from .config import (CORS_ORIGINS,ENABLE_HSTS,MAX_REQUEST_BODY_BYTES,RATE_LIMIT_REQUESTS,RATE_LIMIT_WINDOW_SECONDS,RULE_MAX_FILE_BYTES)
from .config import SESSION_COOKIE_SECURE
from .security import session_application, write_request_error


class AnomalyMonitor:
    """Emit one warning per anomaly and source in each observation window."""

    def __init__(self, logger):
        self.logger = logger
        self.counters = OrderedDict()
        self.lock = threading.Lock()

    def record(self, request: Request, status_code: int):
        path = request.url.path.rstrip("/")
        source = request.client.host if request.client else "unknown"
        if status_code >= 500:
            kind, source, threshold = "server_failures", "all", 5
        elif status_code == 429:
            kind, threshold = "rate_limit_violations", 3
        elif status_code in {400, 401, 403, 404, 422, 423} and request.method == "POST" and path in {
            "/api/auth/login", "/api/auth/reset-password",
        }:
            kind, threshold = "credential_failures", 5
        elif status_code == 403:
            kind, threshold = "access_denials", 5
        else:
            return

        key = (kind, source)
        now = time.monotonic()
        with self.lock:
            start, count = self.counters.get(key, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            count = min(count + 1, threshold + 1)
            self.counters[key] = (start, count)
            self.counters.move_to_end(key)
            if len(self.counters) > 10_000:
                self.counters.popitem(last=False)
        if count == threshold:
            self.logger.warning(
                "CPI_SECURITY_ALERT kind=%s source_ip=%s count=%d window_seconds=60",
                kind, source, count,
            )


def configure_http(app: FastAPI, cors_origins=None, *, require_https: bool = False):
    logger = logging.getLogger("credit_policy_intelligence")
    anomaly_monitor = AnomalyMonitor(logger)
    GENERIC_ERROR_MESSAGE = "An unexpected error occurred. Please try again later."
    INVALID_INPUT_MESSAGE = "Please check the information you entered and try again."
    _request_times: dict[str, deque[float]] = defaultdict(deque)
    _rate_limit_lock = threading.Lock()

    def apply_renewed_session(request: Request, response):
        renewed = getattr(request.state, "renewed_session", None)
        if renewed:
            token, expires_at = renewed
            response.set_cookie(
                session_application(request) + "_session", token, expires=expires_at,
                httponly=True, secure=SESSION_COOKIE_SECURE, samesite="strict", path="/",
            )
        return response


    def audit_error(request: Request, status_code: int, error_code: str, details: str) -> None:
        anomaly_monitor.record(request, status_code)
        try:
            write_request_error(request, status_code, error_code, details)
        except Exception:
            # Audit storage must never replace the original safe response.
            logger.exception("Could not persist an audit error for %s %s", request.method, request.url.path)


    @app.exception_handler(RequestValidationError)
    async def safe_validation_exception_handler(request: Request, error: RequestValidationError):
        if (request.method == "POST" and request.url.path.rstrip("/") == "/api/auth/reset-password"
                and isinstance(error.body, dict)):
            request.state.password_reset_user_id = error.body.get("user_id")
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
            content={"detail": error.detail if isinstance(error.detail, str) else INVALID_INPUT_MESSAGE},
            headers=error.headers,
        )

    @app.exception_handler(DatabaseError)
    async def safe_database_exception_handler(request: Request, error: DatabaseError):
        unavailable = isinstance(error, OperationalError)
        status = 503 if unavailable else 500
        code = "DATABASE_UNAVAILABLE" if unavailable else "DATABASE_ERROR"
        logger.error("Database request failed (%s)", type(error).__name__)
        audit_error(request, status, code, "Database operation failed")
        return JSONResponse(status_code=status, content={"detail": GENERIC_ERROR_MESSAGE})


    @app.exception_handler(Exception)
    async def safe_unhandled_exception_handler(request: Request, error: Exception):
        logger.exception("Unhandled error while processing %s %s", request.method, request.url.path, exc_info=error)
        audit_error(request, 500, "UNHANDLED_SERVER_ERROR", f"{request.method} request failed unexpectedly")
        return apply_renewed_session(
            request, JSONResponse(
                status_code=500, content={"detail": GENERIC_ERROR_MESSAGE},
                headers={"Cache-Control": "no-store, max-age=0"},
            )
        )


    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        client = request.client.host if request.client else "unknown"
        credential_request = request.method == "POST" and request.url.path.rstrip("/") in {
            "/api/auth/login", "/api/auth/recovery", "/api/auth/reset-password",
        }
        key = (client, credential_request)
        window = 60 if credential_request else RATE_LIMIT_WINDOW_SECONDS
        limit = 5 if credential_request else RATE_LIMIT_REQUESTS
        now = time.monotonic()
        with _rate_limit_lock:
            if len(_request_times) >= 10_000:
                stale_clients = [
                    key for key, timestamps in _request_times.items()
                    if not timestamps or timestamps[-1] <= now - max(60, RATE_LIMIT_WINDOW_SECONDS)
                ]
                for key in stale_clients:
                    _request_times.pop(key, None)
                if len(_request_times) >= 10_000 and key not in _request_times:
                    _request_times.pop(next(iter(_request_times)))
            history = _request_times[key]
            cutoff = now - window
            while history and history[0] <= cutoff:
                history.popleft()
            limited = len(history) >= limit
            if not limited:
                history.append(now)

        if limited:
            audit_error(request, 429, "RATE_LIMIT_EXCEEDED", f"{request.method} request exceeded the rate limit")
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please wait and try again."},
                headers={"Retry-After": str(window)},
            )
        elif request.method in {"GET", "HEAD"}:
            async for chunk in request.stream():
                if chunk:
                    audit_error(request, 400, "REQUEST_BODY_NOT_ALLOWED", "Read-only request included a body")
                    response = JSONResponse(
                        status_code=400,
                        content={"detail": "GET and HEAD requests cannot contain a request body."},
                    )
                    break
            else:
                response = await call_next(request)
        else:
            body_limit = RULE_MAX_FILE_BYTES + 1024 * 1024 if request.url.path.startswith('/api/risk-knowledge/assets/') else MAX_REQUEST_BODY_BYTES
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > body_limit:
                audit_error(request, 413, "REQUEST_TOO_LARGE", f"{request.method} request exceeded the size limit")
                response = JSONResponse(status_code=413, content={"detail": "The request is too large."})
            elif request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > body_limit:
                        break
                if len(body) > body_limit:
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
        if ENABLE_HSTS and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return apply_renewed_session(request, response)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Account-User-Id"],
    )

    if require_https:
        @app.middleware("http")
        async def https_only(request: Request, call_next):
            if request.url.scheme != "https":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "HTTPS is required."},
                    headers={"Cache-Control": "no-store"},
                )
            origin = request.headers.get("origin")
            referrer = request.headers.get("referer")
            if ((origin is not None and not origin.startswith("https://"))
                    or (referrer is not None and not referrer.startswith("https://"))):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Requests from insecure pages are not allowed."},
                    headers={"Cache-Control": "no-store"},
                )
            return await call_next(request)

