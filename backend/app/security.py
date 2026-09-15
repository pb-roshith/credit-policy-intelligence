from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
from fastapi import Header, HTTPException
from starlette.concurrency import run_in_threadpool
from .config import SESSIONS
from .database import db_connection, data_schema, user_schema, initialize_user_store

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


def write_admin_log(actor: str, action: str, target: str | None = None, details: str | None = None):
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO public.administrative_logs (actor, action, target, details) VALUES (%s, %s, %s, %s)",
            (actor, action, target, details),
        )


def normalize_answer(answer: str) -> str:
    return " ".join(answer.casefold().split())


def public_user(row: dict) -> dict:
    return {
        "user_id": row["user_id"],
        "role": row["role"],
        "status": row["status"],
        "locked": bool(row["locked"]),
        "failed_attempts": row["failed_attempts"],
        "created_at": row["created_at"],
    }

def resolve_session(authorization: str | None) -> tuple[str, dict]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization[7:]
    session = SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Session is invalid or expired")
    if datetime.now(timezone.utc) >= session["expires_at"]:
        SESSIONS.pop(token, None)
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again")
    return token, session


def create_session(user: dict) -> dict:
    token = secrets.token_urlsafe(32)
    duration = 15 if user["role"] == "admin" else 30
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration)
    SESSIONS[token] = {"user": user, "expires_at": expires_at}
    return {"token": token, "user": user, "expires_at": expires_at.isoformat(), "session_minutes": duration}


def current_admin(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Administrator authentication required")
    _, session = resolve_session(authorization)
    if session["user"]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return session["user"]


async def current_user(authorization: str | None = Header(default=None)):
    _, session = resolve_session(authorization)
    scope = data_schema.set(user_schema(session["user"]["user_id"]))
    try:
        await run_in_threadpool(initialize_user_store)
        yield session["user"]
    finally:
        data_schema.reset(scope)

