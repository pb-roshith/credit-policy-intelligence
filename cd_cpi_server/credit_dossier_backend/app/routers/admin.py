"""Administrator-only application security configuration and audit data."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.auth import hash_password, password_policy, require_admin, validate_password_strength
from app.config import settings
from app.database import get_db
from app.models.user import AuditLog, AuthSession, PasswordPolicyConfiguration, User
from app.schemas.input_validation import StrictInputModel


router = APIRouter(
    prefix="/api/admin",
    tags=["administration"],
    dependencies=[Depends(require_admin)],
)


class PasswordPolicyRequest(StrictInputModel):
    min_length: int = Field(ge=12, le=31)
    max_length: int = Field(ge=12, le=31)
    min_uppercase: int = Field(ge=0, le=1024)
    min_lowercase: int = Field(ge=0, le=1024)
    min_digits: int = Field(ge=0, le=1024)
    min_special: int = Field(ge=0, le=1024)

    @model_validator(mode="after")
    def valid_policy(self):
        if self.min_length > self.max_length:
            raise ValueError("Minimum length cannot exceed maximum length.")
        required_characters = (
            self.min_uppercase
            + self.min_lowercase
            + self.min_digits
            + self.min_special
        )
        if required_characters > self.max_length:
            raise ValueError(
                "Required character counts cannot exceed the maximum password length."
            )
        return self


class AuditLogResponse(BaseModel):
    event_id: str
    category: str
    event_type: str
    user_id: str
    source_ip: str
    resource_id: str
    status: str
    http_status: int
    error_code: str | None = None
    message: str | None
    occurred_at: datetime

    model_config = {"from_attributes": True}


class PendingUserResponse(BaseModel):
    user_id: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LockedUserResponse(BaseModel):
    user_id: str
    role: str
    failed_login_attempts: int
    locked_at: datetime | None

    model_config = {"from_attributes": True}


class AdminResetPasswordRequest(StrictInputModel):
    new_password: str = Field(min_length=1, max_length=31)
    confirm_password: str = Field(min_length=1, max_length=31)


class EncryptionKeyStatusResponse(BaseModel):
    active_version: int
    last_rotated_at: datetime
    next_rotation_at: datetime
    rotation_due: bool


def _sanitized_audit_response(event: AuditLog) -> AuditLogResponse:
    response = AuditLogResponse.model_validate(event)
    if event.category != "system_error":
        return response
    return response.model_copy(
        update={
            "event_type": "system_error",
            "resource_id": "system",
            "message": "A system error occurred. Review restricted server logs for details.",
        }
    )


@router.get("/encryption-key-status", response_model=EncryptionKeyStatusResponse)
def encryption_key_status(request: Request):
    """Encrypted-store rotation is unavailable with .env configuration."""
    request.state.audit_resource_id = "secret-configuration"
    raise HTTPException(status_code=409, detail="Secrets are configured in .env files; automatic encrypted-store key rotation is disabled.")


@router.get("/user-approvals", response_model=list[PendingUserResponse])
def list_pending_user_approvals(request: Request, db: Session = Depends(get_db)):
    request.state.audit_resource_id = "user_approval_queue"
    return (
        db.query(User)
        .filter(User.is_active.is_(True), User.is_approved.is_(False))
        .order_by(User.created_at.asc())
        .all()
    )


@router.post("/user-approvals/{user_id}/approve", response_model=PendingUserResponse)
def approve_user(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized_user_id = user_id.strip().lower()
    request.state.audit_resource_id = f"user:{normalized_user_id}"
    user = db.query(User).filter(User.user_id == normalized_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User ID was not found.")
    if user.is_approved:
        raise HTTPException(status_code=409, detail="This account is already approved.")
    if not user.is_active:
        raise HTTPException(status_code=409, detail="This account is inactive.")
    user.is_approved = True
    user.approved_at = datetime.now(timezone.utc)
    user.approved_by = admin.user_id
    db.commit()
    db.refresh(user)
    return user


@router.get("/locked-users", response_model=list[LockedUserResponse])
def list_locked_users(request: Request, db: Session = Depends(get_db)):
    request.state.audit_resource_id = "locked_user_queue"
    return db.query(User).filter(User.is_locked.is_(True)).order_by(User.locked_at.asc()).all()


@router.post("/locked-users/{user_id}/unlock", response_model=LockedUserResponse)
def unlock_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    normalized_user_id = user_id.strip().lower()
    request.state.audit_resource_id = f"user:{normalized_user_id}"
    user = db.query(User).filter(User.user_id == normalized_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User ID was not found.")
    user.failed_login_attempts = 0
    user.is_locked = False
    user.locked_at = None
    db.commit()
    db.refresh(user)
    return user


@router.post("/locked-users/{user_id}/reset-password")
def admin_reset_password(
    user_id: str,
    data: AdminResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    normalized_user_id = user_id.strip().lower()
    request.state.audit_resource_id = f"user:{normalized_user_id}"
    user = db.query(User).filter(User.user_id == normalized_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User ID was not found.")
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match.")
    try:
        validate_password_strength(data.new_password, user.user_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user.password_hash = hash_password(data.new_password)
    user.credential_version += 1
    user.failed_login_attempts = 0
    user.is_locked = False
    user.locked_at = None
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(synchronize_session=False)
    db.commit()
    return {"message": "Password reset and account unlocked successfully."}


@router.get("/password-policy", response_model=PasswordPolicyRequest)
def get_password_policy(request: Request, db: Session = Depends(get_db)):
    request.state.audit_resource_id = "security_configuration:password_policy"
    return password_policy(db)


@router.put("/password-policy", response_model=PasswordPolicyRequest)
def update_password_policy(
    data: PasswordPolicyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    request.state.audit_resource_id = "security_configuration:password_policy"
    configured = db.get(PasswordPolicyConfiguration, 1)
    values = data.model_dump()
    if configured is None:
        configured = PasswordPolicyConfiguration(id=1, **values)
        db.add(configured)
    else:
        for field, value in values.items():
            setattr(configured, field, value)
    db.commit()
    return values


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(request: Request, db: Session = Depends(get_db)):
    """Return the complete persisted audit trail, newest first."""
    request.state.audit_resource_id = "audit_trail:all"
    events = db.query(AuditLog).order_by(AuditLog.occurred_at.desc()).all()
    return [_sanitized_audit_response(event) for event in events]


@router.get(
    "/administrative-audit-logs",
    response_model=list[AuditLogResponse],
)
def list_administrative_audit_logs(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the complete administrative-action trail, newest first."""
    request.state.audit_resource_id = "audit_trail:administrative_actions"
    events = (
        db.query(AuditLog)
        .filter(AuditLog.category == "administrative_action")
        .order_by(AuditLog.occurred_at.desc())
        .all()
    )
    return [_sanitized_audit_response(event) for event in events]
