"""Persistent HTTP audit logging for user events and system errors."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable

from fastapi import FastAPI, Request
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.models.user import AuditLog, PasswordAuditEvent


logger = logging.getLogger(__name__)
_handler_state = threading.local()


def _source_ip(request: Request) -> str:
    if settings.AUDIT_TRUST_X_FORWARDED_FOR:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _resource_id(request: Request) -> str:
    explicit = getattr(request.state, "audit_resource_id", None)
    if explicit:
        return str(explicit)[:256]
    if request.path_params:
        return ",".join(
            f"{name}:{value}" for name, value in request.path_params.items()
        )[:256]
    return request.url.path[:256]


def _event_type(request: Request) -> str:
    route = request.scope.get("route")
    route_name = getattr(route, "name", None)
    return str(route_name or f"{request.method} {request.url.path}")[:128]


def _category(request: Request, is_error: bool) -> str:
    if is_error:
        return "system_error"
    requested_category = getattr(request.state, "audit_category", "user_event")
    if requested_category == "administrative_action":
        return requested_category
    return "user_event"


def _persist(record: AuditLog, session_factory: Callable = SessionLocal) -> None:
    db = session_factory()
    try:
        db.add(record)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database failure while persisting application audit record.")
    except Exception:
        db.rollback()
        logger.exception("Unexpected failure while persisting application audit record.")
    finally:
        db.close()


def install_audit_middleware(
    app: FastAPI,
    session_factory: Callable = SessionLocal,
) -> None:
    @app.middleware("http")
    async def audit_request(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            event_id = getattr(request.state, "audit_event_id", None) or str(uuid.uuid4())
            request.state.audit_event_id = event_id
            request.state.audit_error_code = "SYS-001"
            _persist(
                AuditLog(
                    event_id=event_id,
                    category="system_error",
                    event_type=_event_type(request),
                    status="error",
                    source_ip=_source_ip(request),
                    user_id=str(getattr(request.state, "audit_user_id", "anonymous"))[:64],
                    resource_id=_resource_id(request),
                    http_status=500,
                    error_code="SYS-001",
                    message="An unexpected server error occurred.",
                ),
                session_factory,
            )
            raise

        is_error = response.status_code >= 500
        is_failure = response.status_code >= 400
        event_id = (
            getattr(request.state, "audit_event_id", None)
            if is_failure
            else None
        )
        _persist(
            AuditLog(
                **({"event_id": event_id} if event_id else {}),
                category=_category(request, is_error),
                event_type=_event_type(request),
                status=(
                    "error"
                    if is_error
                    else "success"
                    if response.status_code < 400
                    else "failure"
                ),
                source_ip=_source_ip(request),
                user_id=str(getattr(request.state, "audit_user_id", "anonymous"))[:64],
                resource_id=_resource_id(request),
                http_status=response.status_code,
                error_code=(
                    getattr(request.state, "audit_error_code", None)
                    if is_failure
                    else None
                ),
                message=f"HTTP {response.status_code}",
            ),
            session_factory,
        )
        return response


class DatabaseAuditLogHandler(logging.Handler):
    """Persist Python ERROR/EXCEPTION logs emitted outside normal HTTP responses."""

    def __init__(self, session_factory: Callable = SessionLocal):
        super().__init__(level=logging.ERROR)
        self.session_factory = session_factory

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(_handler_state, "active", False):
            return
        _handler_state.active = True
        db = self.session_factory()
        try:
            db.add(
                AuditLog(
                    category="system_error",
                    event_type=f"python_error:{record.name}"[:128],
                    status="error",
                    source_ip="system",
                    user_id="system",
                    resource_id=f"{record.module}:{record.lineno}"[:256],
                    http_status=500,
                    error_code="SYS-001",
                    message="A background system error occurred. Review restricted server logs for details.",
                )
            )
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            # Logging must never recursively fail the application.
        except Exception:
            db.rollback()
        finally:
            db.close()
            _handler_state.active = False


def install_system_error_logging(
    session_factory: Callable = SessionLocal,
) -> DatabaseAuditLogHandler:
    root_logger = logging.getLogger()
    existing = next(
        (
            handler
            for handler in root_logger.handlers
            if isinstance(handler, DatabaseAuditLogHandler)
        ),
        None,
    )
    if existing:
        return existing
    handler = DatabaseAuditLogHandler(session_factory)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root_logger.addHandler(handler)
    return handler


def migrate_legacy_password_audit(db) -> int:
    """Preserve password-only audit rows created before the unified trail."""
    migrated = 0
    for legacy in db.query(PasswordAuditEvent).all():
        if db.get(AuditLog, legacy.id):
            continue
        db.add(
            AuditLog(
                event_id=legacy.id,
                occurred_at=legacy.occurred_at,
                category="user_event",
                event_type=legacy.event_type,
                status=legacy.status,
                source_ip="not_captured",
                user_id=legacy.user_id,
                resource_id=f"user:{legacy.user_id}",
                http_status=200 if legacy.status == "success" else 400,
                error_code=None if legacy.status == "success" else "REQ-002",
                message="Migrated legacy password audit event.",
            )
        )
        migrated += 1
    if migrated:
        db.commit()
    return migrated
