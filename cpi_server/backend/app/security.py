from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool
from .config import ADMIN_USER_ID
from .database import db_connection, account_user_id, ensure_account_defaults, retry_on_db_conflict

def hash_secret(value: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, 310_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_secret(value: str, stored: str) -> bool:
    try:
        salt_hex, _ = stored.split(":", 1)
        return hmac.compare_digest(hash_secret(value, bytes.fromhex(salt_hex)), stored)
    except (ValueError, TypeError):
        return False


def get_password_policy() -> dict:
    with db_connection() as connection:
        return connection.execute("SELECT * FROM public.password_policy WHERE id = 1").fetchone()


def password_errors(password: str, user_id: str) -> list[str]:
    policy = get_password_policy()
    uppercase_count = len(re.findall(r"[A-Z]", password))
    lowercase_count = len(re.findall(r"[a-z]", password))
    digit_count = len(re.findall(r"[0-9]", password))
    special_count = len(re.findall(r"[^A-Za-z0-9]", password))
    checks = [
        (len(password) >= policy["minimum_length"], f"Password must contain at least {policy['minimum_length']} characters"),
        (len(password) <= policy["maximum_length"], f"Password must contain no more than {policy['maximum_length']} characters"),
        (uppercase_count >= policy["minimum_uppercase"], f"Password must contain at least {policy['minimum_uppercase']} uppercase character(s)"),
        (lowercase_count >= policy["minimum_lowercase"], f"Password must contain at least {policy['minimum_lowercase']} lowercase character(s)"),
        (digit_count >= policy["minimum_digits"], f"Password must contain at least {policy['minimum_digits']} digit(s)"),
        (special_count >= policy["minimum_special"], f"Password must contain at least {policy['minimum_special']} special character(s)"),
        (user_id.strip().casefold() not in password.casefold(), "Password must not contain the user ID"),
    ]
    return [message for passed, message in checks if not passed]


@retry_on_db_conflict
def write_admin_log(actor: str, action: str, target: str | None = None,
                    details: str | None = None, source_ip: str | None = None,
                    event_type: str = "event", outcome: str = "success",
                    severity: str = "info", error_code: str | None = None):
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO public.administrative_logs "
            "(actor, action, target, source_ip, event_type, outcome, severity, error_code, details) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (actor, action, target, source_ip, event_type, outcome, severity, error_code, details),
        )


@retry_on_db_conflict
def write_user_log(action_owner_id: str, action: str, resource_id: str | None = None,
                   details: str | None = None, source_ip: str | None = None,
                   event_type: str = "event", outcome: str = "success",
                   severity: str = "info", error_code: str | None = None):
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO public.user_logs "
            "(source_ip, action_owner_id, action, resource_id, event_type, outcome, severity, error_code, details) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (source_ip, action_owner_id, action, resource_id, event_type, outcome, severity, error_code, details),
        )


def write_request_error(request: Request, status_code: int, error_code: str, details: str) -> None:
    """Write a sanitized request failure to the audit tables without reading its body."""
    actor = "anonymous"
    role = None
    application=session_application(request)
    token = request.cookies.get(application+"_session")
    if token:
        with db_connection() as connection:
            session = connection.execute(
                "SELECT user_id, role FROM public.sessions WHERE token_hash = %s AND application_id=%s",
                (_session_token_hash(token),application),
            ).fetchone()
        if session:
            actor = session["user_id"]
            role = session["role"]

    path = request.url.path[:128]
    ip_address = request.client.host if request.client else None
    severity = "critical" if status_code >= 500 else "warning"
    if role == "admin" or path.startswith("/api/admin"):
        write_admin_log(
            actor, "HTTP_REQUEST_FAILED", path, details, ip_address,
            "error", "failure", severity, error_code,
        )
    else:
        write_user_log(
            actor, "HTTP_REQUEST_FAILED", path, details, ip_address,
            "error", "failure", severity, error_code,
        )


def normalize_answer(answer: str) -> str:
    return " ".join(answer.casefold().split())


def public_user(row: dict) -> dict:
    return {
        "auth_provider": row.get("auth_provider", "local"),
        "dossier_user_id": row.get("dossier_user_id"),
        "dossier_credential_version": row.get("dossier_credential_version"),
        "user_id": row["user_id"],
        "role": row["role"],
        "status": row["status"],
        "locked": bool(row["locked"]),
        "failed_attempts": row["failed_attempts"],
        "created_at": row["created_at"],
    }


def _session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def session_application(request:Request) -> str:
    scope=getattr(request,'scope',{})
    app=scope.get('app') if isinstance(scope,dict) else None
    return 'dm' if getattr(getattr(app,'state',None),'application_id',None)=='dm' else 'cpi'


def resolve_session(request: Request) -> tuple[str, dict]:
    application=session_application(request)
    token = request.cookies.get(application+"_session")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    token_hash = _session_token_hash(token)
    with db_connection() as connection:
        stored = connection.execute(
            "SELECT user_id, role, expires_at, csrf_token_hash FROM public.sessions "
            "WHERE token_hash = %s AND application_id = %s AND expires_at > CURRENT_TIMESTAMP",
            (token_hash,application),
        ).fetchone()
        if not stored:
            connection.execute("DELETE FROM public.sessions WHERE token_hash = %s AND application_id=%s", (token_hash,application))
            raise HTTPException(status_code=401, detail="Session is invalid or expired")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            csrf_token = request.headers.get("X-CSRF-Token", "")
            if not csrf_token or not hmac.compare_digest(_session_token_hash(csrf_token), stored["csrf_token_hash"]):
                raise HTTPException(status_code=403, detail="Request verification failed")

        if stored["role"] == "admin":
            if not hmac.compare_digest(stored["user_id"].casefold(), ADMIN_USER_ID.casefold()):
                connection.execute("DELETE FROM public.sessions WHERE token_hash = %s", (token_hash,))
                raise HTTPException(status_code=401, detail="Session is invalid or expired")
            user = {"user_id": ADMIN_USER_ID, "role": "admin", "status": "active", "locked": False}
        else:
            row = connection.execute(
                "SELECT * FROM public.users WHERE LOWER(user_id) = LOWER(%s)",
                (stored["user_id"],),
            ).fetchone()
            if not row or row["status"] != "approved" or row["locked"] or row["role"] != stored["role"]:
                connection.execute("DELETE FROM public.sessions WHERE token_hash = %s", (token_hash,))
                raise HTTPException(status_code=401, detail="Session is invalid or expired")
            user = public_user(row)
    if user.get("auth_provider") == "dossier":
        from .services.shared_deals import call_shared_deals
        try:
            identity = call_shared_deals(user, path="/identity")
        except HTTPException as error:
            if error.status_code in {401, 403, 423}:
                revoke_session(token)
                raise HTTPException(401, "Your Credit Dossier account is unavailable. Please sign in again.") from error
            raise
        if (identity["user_id"] != user["dossier_user_id"] or identity["role"] != user["role"]
                or identity.get('credential_version') != user.get('dossier_credential_version')):
            revoke_session(token)
            raise HTTPException(401, "Your Credit Dossier account has changed. Please sign in again.")
    session = {"user": user, "expires_at": stored["expires_at"]}
    return token, session


@retry_on_db_conflict
def create_session(user: dict,application: str="cpi") -> dict:
    if application not in {"cpi","dm"}:raise ValueError("Unknown application")
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    duration = 15 if user["role"] == "admin" else 30
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration)
    with db_connection() as connection:
        connection.execute("DELETE FROM public.sessions WHERE expires_at <= CURRENT_TIMESTAMP")
        connection.execute(
            "DELETE FROM public.sessions WHERE LOWER(user_id) = LOWER(%s) AND application_id = %s",
            (user["user_id"],application),
        )
        connection.execute(
            "INSERT INTO public.sessions (token_hash, csrf_token_hash, user_id, role, expires_at, application_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (_session_token_hash(token), _session_token_hash(csrf_token), user["user_id"], user["role"], expires_at,application),
        )
    return {"token": token, "csrf_token": csrf_token, "user": user, "expires_at": expires_at.isoformat(), "session_minutes": duration}


@retry_on_db_conflict
def revoke_session(token: str) -> dict | None:
    with db_connection() as connection:
        return connection.execute(
            "DELETE FROM public.sessions WHERE token_hash = %s RETURNING user_id, role",
            (_session_token_hash(token),),
        ).fetchone()


@retry_on_db_conflict
def revoke_user_sessions(user_id: str) -> None:
    with db_connection() as connection:
        connection.execute("DELETE FROM public.sessions WHERE LOWER(user_id) = LOWER(%s)", (user_id,))


def current_admin(request: Request):
    _, session = resolve_session(request)
    if session["user"]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return session["user"]


async def current_user(request: Request):
    _, session = await run_in_threadpool(resolve_session, request)
    selected_account = request.headers.get("X-Account-User-Id")
    actor = session["user"]
    if selected_account and selected_account != actor['user_id']:
        if actor['role'] != 'credit_analyst':
            raise HTTPException(403, 'Only credit analysts can view another relationship manager account.')
        def validate_account():
            with db_connection() as connection:
                return connection.execute("SELECT 1 FROM public.users WHERE user_id=%s AND role='relationship_manager'", (selected_account,)).fetchone()
        if not await run_in_threadpool(validate_account):
            raise HTTPException(404, 'Relationship manager account not found.')
    scope = account_user_id.set(selected_account or actor['user_id'])
    try:
        await run_in_threadpool(ensure_account_defaults)
        yield session["user"]
    finally:
        account_user_id.reset(scope)

