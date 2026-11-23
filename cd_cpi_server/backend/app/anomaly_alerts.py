"""Detect and deduplicate security and operational alerts from HTTP audit events."""

from datetime import datetime, timedelta, timezone
from hashlib import blake2b

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from app.models.user import AuditLog


ALERT_CATEGORIES = ("security_alert", "operational_alert")
ALERT_WINDOW = timedelta(minutes=10)
LOGIN_EVENTS = ("login", "authenticate_identity")
LOCKOUT_EVENT = "account_locked_after_failed_sign_in"
UNKNOWN_IDENTITY_EVENT = "shared_identity_not_found"
ADMIN_DENIED_EVENT = "admin_access_denied"


def _failed_login(event: AuditLog) -> bool:
    return (
        (event.event_type in LOGIN_EVENTS and event.http_status in {401, 423})
        or event.event_type in {LOCKOUT_EVENT, UNKNOWN_IDENTITY_EVENT}
    )


def is_anomaly_candidate(event: AuditLog) -> bool:
    return _failed_login(event) or event.event_type == ADMIN_DENIED_EVENT or event.http_status >= 500


def _maybe_alert(
    db: Session,
    event: AuditLog,
    *,
    code: str,
    event_type: str,
    message: str,
    category: str = "security_alert",
    scope: str,
    threshold: int,
    matching,
    window: timedelta = ALERT_WINDOW,
) -> AuditLog | None:
    # Serialize matching checks across workers so concurrent requests cannot duplicate an alert.
    if db.get_bind().dialect.name == "postgresql":
        key = blake2b(f"cd_cpi_alert:{code}:{scope}".encode(), digest_size=8).digest()
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int.from_bytes(key, "big", signed=True)})
    since = datetime.now(timezone.utc) - window
    base = select(AuditLog.event_id).where(AuditLog.occurred_at >= since)
    if db.scalar(base.where(AuditLog.error_code == code, AuditLog.resource_id == scope).limit(1)):
        return None
    if threshold > 1 and not db.scalar(base.where(matching).offset(threshold - 1).limit(1)):
        return None
    alert = AuditLog(
        category=category,
        event_type=event_type,
        status="warning" if category == "security_alert" else "error",
        source_ip=event.source_ip if category == "security_alert" else "system",
        user_id=event.user_id if event.event_type in {LOCKOUT_EVENT, ADMIN_DENIED_EVENT} else "system",
        resource_id=scope,
        http_status=event.http_status,
        error_code=code,
        message=message,
    )
    db.add(alert)
    return alert


def detect_anomalies(db: Session, event: AuditLog) -> list[AuditLog]:
    alerts = []
    if event.event_type == LOCKOUT_EVENT:
        alerts.append(_maybe_alert(
            db, event, code="SEC-ALERT-001", event_type="account_lockout",
            message="An account was locked after repeated failed sign-in attempts.",
            scope=event.resource_id, threshold=1, matching=None,
        ))

    if _failed_login(event) and event.source_ip != "unknown":
        alerts.append(_maybe_alert(
            db, event, code="SEC-ALERT-002", event_type="repeated_failed_sign_in",
            message="At least five sign-in failures came from the same source within ten minutes.",
            scope=f"source:{event.source_ip}", threshold=5,
            matching=and_(
                AuditLog.source_ip == event.source_ip,
                or_(
                    and_(AuditLog.event_type.in_(LOGIN_EVENTS), AuditLog.http_status.in_((401, 423))),
                    AuditLog.event_type.in_((LOCKOUT_EVENT, UNKNOWN_IDENTITY_EVENT)),
                ),
            ),
        ))

    if event.event_type == ADMIN_DENIED_EVENT:
        alerts.append(_maybe_alert(
            db, event, code="SEC-ALERT-003", event_type="repeated_admin_access_denial",
            message="An account was denied administrator access at least three times within ten minutes.",
            scope=f"user:{event.user_id}", threshold=3,
            matching=and_(AuditLog.event_type == ADMIN_DENIED_EVENT, AuditLog.user_id == event.user_id),
        ))

    if event.http_status >= 500:
        alerts.append(_maybe_alert(
            db, event, code="OPS-ALERT-001", event_type="repeated_server_errors",
            message="The API returned at least five server errors within ten minutes.",
            category="operational_alert", scope="service:api", threshold=5,
            matching=and_(
                AuditLog.category == "system_error",
                AuditLog.http_status >= 500,
                AuditLog.source_ip != "system",
            ),
        ))
    return [alert for alert in alerts if alert is not None]
