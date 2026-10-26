"""Stable application error codes, canonical messages, and correlation helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class ErrorDefinition:
    code: str
    http_status: int
    message: str
    description: str


def _error(code: str, status: int, message: str, description: str) -> ErrorDefinition:
    return ErrorDefinition(code, status, message, description)


ERROR_CATALOG: dict[str, ErrorDefinition] = {
    "REQ-001": _error("REQ-001", 422, "The request contains invalid data.", "Request schema validation failed."),
    "REQ-002": _error("REQ-002", 400, "The request could not be processed.", "Generic invalid request."),
    "AUTH-001": _error("AUTH-001", 401, "Invalid user ID or password.", "Credential verification failed."),
    "AUTH-002": _error("AUTH-002", 403, "Your account is in the admin queue for approval.", "Account approval is pending."),
    "AUTH-003": _error("AUTH-003", 401, "Please sign in to continue.", "No valid session was supplied."),
    "AUTH-004": _error("AUTH-004", 401, "Your session is invalid. Please sign in again.", "Session identifier was not recognized."),
    "AUTH-005": _error("AUTH-005", 401, "Your session has expired. Please sign in again.", "Session lifetime elapsed."),
    "AUTH-006": _error("AUTH-006", 401, "This user account is inactive.", "Account is inactive or unapproved."),
    "AUTH-007": _error("AUTH-007", 403, "You do not have permission to perform this action.", "Role authorization failed."),
    "AUTH-008": _error("AUTH-008", 400, "The password does not satisfy the configured policy.", "Password policy validation failed."),
    "AUTH-009": _error(
        "AUTH-009",
        423,
        "Your account is locked. Reset your password using your security questions or contact an administrator.",
        "Three consecutive credential failures locked the account.",
    ),
    "USER-001": _error("USER-001", 409, "That user ID is already registered.", "User identifier conflict."),
    "USER-002": _error("USER-002", 404, "User ID was not found.", "User lookup failed."),
    "USER-003": _error("USER-003", 409, "This account is already approved.", "Account approval conflict."),
    "USER-004": _error("USER-004", 409, "This account is inactive.", "Inactive account cannot be approved."),
    "DEAL-001": _error("DEAL-001", 404, "Deal not found.", "Deal lookup failed."),
    "SECTION-001": _error("SECTION-001", 404, "Section not found.", "Section lookup failed."),
    "DOCUMENT-001": _error("DOCUMENT-001", 404, "Document not found.", "Document lookup failed."),
    "UPLOAD-001": _error("UPLOAD-001", 404, "Upload not found.", "Upload lookup failed."),
    "VERSION-001": _error("VERSION-001", 404, "Version not found.", "Version lookup failed."),
    "JOB-001": _error("JOB-001", 404, "Generation job not found.", "Background generation job lookup failed."),
    "RESOURCE-001": _error("RESOURCE-001", 404, "The requested resource was not found.", "Generic resource lookup failed."),
    "STATE-001": _error("STATE-001", 409, "The operation conflicts with the current resource state.", "Resource state conflict."),
    "FILE-001": _error("FILE-001", 400, "The uploaded file is invalid or unsupported.", "File allowlist or signature validation failed."),
    "LIBRARY-001": _error("LIBRARY-001", 404, "Library file not found.", "Library document lookup failed."),
    "LIBRARY-002": _error("LIBRARY-002", 409, "The document library is still synchronizing.", "Library synchronization blocks the operation."),
    "LIBRARY-003": _error("LIBRARY-003", 502, "The document library is temporarily unavailable.", "Library initialization or access failed."),
    "GEN-001": _error("GEN-001", 400, "Section generation could not be completed with the supplied inputs.", "Generation input validation failed."),
    "GEN-002": _error("GEN-002", 500, "Content generation failed.", "Unexpected content-generation failure."),
    "DB-001": _error("DB-001", 409, "The request conflicts with existing data.", "Database integrity constraint failed."),
    "DB-002": _error("DB-002", 400, "One or more supplied values are invalid.", "Database rejected supplied data."),
    "DB-003": _error("DB-003", 503, "The database is temporarily unavailable. Please try again.", "Database operational failure."),
    "DB-004": _error("DB-004", 500, "A database operation failed.", "Unhandled database failure."),
    "EXT-001": _error("EXT-001", 504, "An external service timed out. Please try again.", "Upstream timeout."),
    "EXT-002": _error("EXT-002", 502, "An external service is unavailable. Please try again.", "Upstream HTTP failure."),
    "SYS-001": _error("SYS-001", 500, "An unexpected server error occurred.", "Unhandled application failure."),
}


_DETAIL_CODES = {
    "Invalid user ID or password.": "AUTH-001",
    "Your account is in the admin queue for approval.": "AUTH-002",
    "Please sign in to continue.": "AUTH-003",
    "Your session is invalid. Please sign in again.": "AUTH-004",
    "Your session has expired. Please sign in again.": "AUTH-005",
    "This user account is inactive.": "AUTH-006",
    "That user ID is already registered.": "USER-001",
    "User ID was not found.": "USER-002",
    "This account is already approved.": "USER-003",
    "This account is inactive.": "USER-004",
    "Deal not found": "DEAL-001",
    "Deal not found.": "DEAL-001",
    "Section not found": "SECTION-001",
    "Section not found.": "SECTION-001",
    "Document not found": "DOCUMENT-001",
    "Document not found.": "DOCUMENT-001",
    "Upload not found": "UPLOAD-001",
    "Upload not found.": "UPLOAD-001",
    "Version not found": "VERSION-001",
    "Version not found.": "VERSION-001",
    "Draft All job not found": "JOB-001",
    "Library file not found": "LIBRARY-001",
    "Unable to initialize the document library.": "LIBRARY-003",
    "Section generation could not be completed with the supplied inputs.": "GEN-001",
}


def resolve_http_error_code(status_code: int, detail: object) -> str:
    """Map legacy FastAPI exceptions into the centralized catalog."""
    text = detail if isinstance(detail, str) else ""
    if text in _DETAIL_CODES:
        return _DETAIL_CODES[text]
    lowered = text.casefold()
    if status_code == 423:
        return "AUTH-009"
    if text.startswith("Invalid user ID or password."):
        return "AUTH-001"
    if any(term in lowered for term in ("unsupported file", "uploaded file", "file content")):
        return "FILE-001"
    if "password must" in lowered or "password policy" in lowered:
        return "AUTH-008"
    if "library sync" in lowered or "library is still" in lowered:
        return "LIBRARY-002"
    if status_code == 401:
        return "AUTH-003"
    if status_code == 403:
        return "AUTH-007"
    if status_code == 404:
        return "RESOURCE-001"
    if status_code == 409:
        return "STATE-001"
    if status_code >= 500:
        return "SYS-001"
    return "REQ-002"


def error_payload(request: Request, code: str) -> dict[str, str]:
    definition = ERROR_CATALOG[code]
    event_id = getattr(request.state, "audit_event_id", None) or str(uuid.uuid4())
    request.state.audit_event_id = event_id
    request.state.audit_error_code = code
    return {"error_code": code, "detail": definition.message, "event_id": event_id}


def error_response(
    request: Request,
    code: str,
    *,
    status_code: int | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    definition = ERROR_CATALOG[code]
    return JSONResponse(
        status_code=status_code or definition.http_status,
        content=error_payload(request, code),
        headers=headers,
    )
