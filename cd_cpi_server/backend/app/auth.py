"""Password hashing, session creation, and FastAPI authorization dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import re
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.anomaly_alerts import ADMIN_DENIED_EVENT, LOCKOUT_EVENT
from app.database import get_db
from app.models.user import AuthSession, PasswordPolicyConfiguration, User
from app.config import settings


SESSION_COOKIE = "credit_dossier_session"
PBKDF2_ITERATIONS = 600_000
ALLOWED_ROLES = {"relationship_manager", "credit_analyst", "admin"}


def find_login_user(db: Session, user_id: str, *, case_insensitive: bool = False):
    user = db.query(User).filter(User.user_id == user_id.strip()).with_for_update().first()
    if not user and case_insensitive:
        from sqlalchemy import func
        matches = db.query(User).filter(func.lower(User.user_id) == user_id.strip().lower()).with_for_update().all()
        user = matches[0] if len(matches) == 1 else None
    return user


def authenticate_user(
    db: Session, user_id: str, password: str, *, request: Request | None = None,
    case_insensitive: bool = False,
):
    """One password/approval/lockout check shared by Dossier and CPI sign-in."""
    user = find_login_user(db, user_id, case_insensitive=case_insensitive)
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid user ID or password.")
    if not user.is_approved:
        raise HTTPException(403, "Your account is in the admin queue for approval.")
    if user.is_locked:
        raise HTTPException(423, "Your account is locked. Reset your password in either application or contact an administrator.")
    if not verify_password(password, user.password_hash):
        if user.role == "admin":
            raise HTTPException(401, "Invalid user ID or password.")
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 3:
            user.is_locked = True
            user.locked_at = datetime.now(timezone.utc)
            db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(synchronize_session=False)
        db.commit()
        if user.is_locked:
            if request is not None:
                request.state.audit_event_type = LOCKOUT_EVENT
                request.state.audit_user_id = user.user_id
                request.state.audit_resource_id = f"user:{user.user_id}"
            raise HTTPException(423, "Your account has been locked after 3 failed sign-in attempts. Reset your password in either application.")
        raise HTTPException(401, f"Invalid user ID or password. {3 - user.failed_login_attempts} attempts remaining.")
    user.failed_login_attempts = 0
    user.locked_at = None
    db.commit()
    return user


def session_timeout_minutes(role: str) -> int:
    return {
        "relationship_manager": settings.SESSION_TIMEOUT_RELATIONSHIP_MANAGER_MINUTES,
        "credit_analyst": settings.SESSION_TIMEOUT_CREDIT_ANALYST_MINUTES,
        "admin": settings.SESSION_TIMEOUT_ADMIN_MINUTES,
    }.get(role, settings.SESSION_TIMEOUT_ADMIN_MINUTES)


def default_password_policy() -> dict[str, int]:
    return {
        "min_length": max(12, min(settings.PASSWORD_MIN_LENGTH, 31)),
        "max_length": max(12, min(settings.PASSWORD_MAX_LENGTH, 31)),
        "min_uppercase": settings.PASSWORD_MIN_UPPERCASE,
        "min_lowercase": settings.PASSWORD_MIN_LOWERCASE,
        "min_digits": settings.PASSWORD_MIN_DIGITS,
        "min_special": settings.PASSWORD_MIN_SPECIAL,
    }


def password_policy(db: Session | None = None) -> dict[str, int]:
    if db is not None:
        configured = db.get(PasswordPolicyConfiguration, 1)
        if configured:
            return {
                "min_length": max(12, min(configured.min_length, 31)),
                "max_length": max(12, min(configured.max_length, 31)),
                "min_uppercase": configured.min_uppercase,
                "min_lowercase": configured.min_lowercase,
                "min_digits": configured.min_digits,
                "min_special": configured.min_special,
            }
    return default_password_policy()


def password_policy_checks(
    password: str,
    user_id: str | None = None,
    db: Session | None = None,
) -> list[dict[str, object]]:
    """Return each configured policy rule and whether the password satisfies it."""
    policy = password_policy(db)
    checks: list[dict[str, object]] = [
        {
            "key": "min_length",
            "label": f"At least {policy['min_length']} characters",
            "met": len(password) >= policy["min_length"],
        },
        {
            "key": "max_length",
            "label": f"No more than {policy['max_length']} characters",
            "met": len(password) <= policy["max_length"],
        },
    ]
    character_rules = (
        ("uppercase", "uppercase letter", r"[A-Z]", policy["min_uppercase"]),
        ("lowercase", "lowercase letter", r"[a-z]", policy["min_lowercase"]),
        ("digits", "number", r"\d", policy["min_digits"]),
        ("special", "special character", r"[^A-Za-z0-9]", policy["min_special"]),
    )
    for key, singular_label, pattern, required in character_rules:
        if required:
            checks.append({
                "key": key,
                "label": f"At least {required} {singular_label}{'' if required == 1 else 's'}",
                "met": len(re.findall(pattern, password)) >= required,
            })
    if user_id:
        checks.append({
            "key": "user_id",
            "label": "Does not contain your user ID",
            "met": user_id.lower() not in password.lower(),
        })
    return checks


def validate_password_strength(
    password: str,
    user_id: str | None = None,
    db: Session | None = None,
) -> None:
    """Enforce the password policy for registration and password changes."""
    unmet = [
        str(check["label"])
        for check in password_policy_checks(password, user_id, db)
        if not check["met"]
    ]
    if unmet:
        raise ValueError("Password must satisfy: " + "; ".join(unmet) + ".")


def normalize_security_answer(answer: str) -> str:
    """Make recovery answers insensitive to case and repeated surrounding whitespace."""
    return " ".join(answer.strip().casefold().split())


def hash_security_answer(answer: str) -> str:
    return hash_password(normalize_security_answer(answer))


def verify_security_answer(answer: str, encoded: str) -> bool:
    return verify_password(normalize_security_answer(answer), encoded)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_session(db: Session, user: User) -> tuple[str, AuthSession]:
    # Serialize concurrent logins for the same account and replace its session.
    db.query(User.id).filter(User.id == user.id).with_for_update().one()
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(
        synchronize_session=False
    )
    raw_token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    session = AuthSession(
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        user_id=user.id,
        expires_at=now + timedelta(minutes=session_timeout_minutes(user.role)),
    )
    db.add(session)
    db.commit()
    return raw_token, session


def cap_existing_session_expirations(db: Session) -> int:
    """Shorten legacy sessions so stored expirations obey current role limits."""
    changed = 0
    for auth_session in db.query(AuthSession).all():
        created_at = auth_session.created_at
        expires_at = auth_session.expires_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        role = auth_session.user.role if auth_session.user else "admin"
        maximum_expiry = created_at + timedelta(minutes=session_timeout_minutes(role))
        if expires_at > maximum_expiry:
            auth_session.expires_at = maximum_expiry
            changed += 1
    if changed:
        db.commit()
    return changed


def seed_initial_users(db: Session) -> None:
    """Create initial accounts and reconcile the configured admin bootstrap."""
    accounts = (
        (
            settings.INITIAL_RELATIONSHIP_MANAGER_USER_ID,
            settings.INITIAL_RELATIONSHIP_MANAGER_PASSWORD,
            "relationship_manager",
        ),
        (
            settings.INITIAL_CREDIT_ANALYST_USER_ID,
            settings.INITIAL_CREDIT_ANALYST_PASSWORD,
            "credit_analyst",
        ),
        (
            settings.INITIAL_ADMIN_USER_ID,
            settings.INITIAL_ADMIN_PASSWORD,
            "admin",
        ),
    )
    changed = False
    for configured_user_id, password, role in accounts:
        user_id = configured_user_id.strip().lower()
        if not user_id or not password:
            continue
        existing = db.query(User).filter(User.user_id == user_id).first()
        if existing:
            # A configured admin ID is an explicit bootstrap instruction. Repair
            # an older account that used the same ID and was assigned a legacy
            # role, but do not overwrite later password changes once it is admin.
            if role == "admin" and existing.role != "admin":
                validate_password_strength(password, user_id, db)
                existing.role = "admin"
                existing.password_hash = hash_password(password)
                existing.is_active = True
                existing.is_approved = True
                changed = True
            continue
        validate_password_strength(password, user_id, db)
        db.add(
            User(
                user_id=user_id,
                password_hash=hash_password(password),
                role=role,
                is_approved=True,
            )
        )
        changed = True
    changed = bool(
        db.query(User).filter(User.role == "normal").update(
            {User.role: "credit_analyst"}, synchronize_session=False
        )
    ) or changed
    if changed:
        db.commit()


def _unauthorized(detail: str = "Please sign in to continue.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        raise _unauthorized()

    token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
    auth_session = (
        db.query(AuthSession).filter(AuthSession.token_hash == token_hash).first()
    )
    if not auth_session:
        raise _unauthorized("Your session is invalid. Please sign in again.")

    user = auth_session.user
    if not user or not user.is_active or not user.is_approved:
        raise _unauthorized("This user account is inactive.")
    request.state.audit_user_id = user.user_id

    expires_at = auth_session.expires_at
    created_at = auth_session.created_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    role_expiry = created_at + timedelta(minutes=session_timeout_minutes(user.role))
    effective_expiry = min(expires_at, role_expiry)
    if effective_expiry <= datetime.now(timezone.utc):
        db.delete(auth_session)
        db.commit()
        raise _unauthorized("Your session has expired. Please sign in again.")

    return user


def require_deal_owner(
    deal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allow an RM to access owned deals and a Credit Analyst to access all deals."""
    from app.models.deal import Deal

    query = db.query(Deal).filter(Deal.id == deal_id)
    if current_user.role == "relationship_manager":
        query = query.filter(Deal.owner_user_id == current_user.id)
    elif current_user.role != "credit_analyst":
        raise HTTPException(status_code=403, detail="Your role cannot access deals.")
    deal = query.first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found.")
    return deal


def require_relationship_manager(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "relationship_manager":
        raise HTTPException(
            status_code=403,
            detail="Only Relationship Managers can create or submit deals.",
        )
    return current_user


def require_credit_analyst(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "credit_analyst":
        raise HTTPException(
            status_code=403,
            detail="Only Credit Analysts can approve deals.",
        )
    return current_user


def require_admin(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        request.state.audit_event_type = ADMIN_DENIED_EVENT
        raise HTTPException(
            status_code=403,
            detail="Only administrators can manage application security settings.",
        )
    # The audit middleware persists administrator activity separately from
    # ordinary user events after the response status is known.
    request.state.audit_category = "administrative_action"
    return current_user
