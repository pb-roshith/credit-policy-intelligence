"""HTTP method and browser-origin controls."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _has_request_data(request: Request) -> bool:
    if request.url.query:
        return True
    content_length = request.headers.get("content-length", "").strip()
    try:
        if content_length and int(content_length) > 0:
            return True
    except ValueError:
        return True
    return "chunked" in request.headers.get("transfer-encoding", "").lower()


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return request.headers.get("sec-fetch-site", "").lower() != "cross-site"
    normalized_origin = origin.rstrip("/")
    if normalized_origin in settings.cors_allowed_origins:
        return True
    parsed = urlsplit(normalized_origin)
    request_host = request.headers.get("host", "").casefold()
    origin_host = parsed.netloc.casefold()
    return parsed.scheme in {"http", "https"} and origin_host == request_host


def install_request_security_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def enforce_request_security(request: Request, call_next):
        if request.method in {"GET", "HEAD"} and _has_request_data(request):
            return JSONResponse(
                status_code=405,
                content={"detail": "GET and HEAD requests must not contain body or query data; use POST."},
                headers={"Allow": "POST", "Cache-Control": "no-store"},
            )
        if request.method not in _SAFE_METHODS and not _same_origin(request):
            return JSONResponse(
                status_code=403,
                content={"detail": "Cross-origin state-changing requests are not allowed."},
                headers={"Cache-Control": "no-store"},
            )
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'; object-src 'none'",
        )
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        if settings.APP_ENV.casefold() == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
