"""Login, registration, logout, and current-user endpoints."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.auth import (
    SESSION_COOKIE,
    create_session,
    get_current_user,
    hash_password,
    hash_security_answer,
    normalize_security_answer,
    password_policy,
    session_timeout_minutes,
    validate_password_strength,
    verify_password,
    verify_security_answer,
)
from app.config import settings
from app.database import get_db
from app.models.user import AuthSession, SecurityAnswer, User
from app.schemas.input_validation import StrictInputModel


router = APIRouter(prefix="/api/auth", tags=["authentication"])
logger = logging.getLogger(__name__)
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class Credentials(StrictInputModel):
    user_id: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("user_id")
    @classmethod
    def valid_user_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not USER_ID_PATTERN.fullmatch(value):
            raise ValueError("Use only letters, numbers, periods, hyphens, or underscores.")
        return value


class SecurityQuestionResponse(StrictInputModel):
    question: str = Field(min_length=1, max_length=256)
    answer: str = Field(min_length=1, max_length=256)

    @field_validator("question", "answer")
    @classmethod
    def strip_value(cls, value: str) -> str:
        return value.strip()


class RegisterRequest(Credentials):
    confirm_password: str = Field(min_length=1, max_length=31)
    role: str
    security_questions: list[SecurityQuestionResponse] = Field(min_length=3, max_length=3)

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        if value not in {"relationship_manager", "credit_analyst"}:
            raise ValueError("Role must be Relationship Manager or Credit Analyst.")
        return value


class ChangePasswordRequest(StrictInputModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=31)
    confirm_password: str = Field(min_length=1, max_length=31)


class UserIdRequest(StrictInputModel):
    user_id: str = Field(min_length=3, max_length=64)

    @field_validator("user_id")
    @classmethod
    def valid_user_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not USER_ID_PATTERN.fullmatch(value):
            raise ValueError("Use only letters, numbers, periods, hyphens, or underscores.")
        return value


class ResetPasswordRequest(UserIdRequest):
    security_questions: list[SecurityQuestionResponse] = Field(min_length=3, max_length=3)
    new_password: str = Field(min_length=1, max_length=31)
    confirm_password: str = Field(min_length=1, max_length=31)


class ConfigureSecurityQuestionsRequest(StrictInputModel):
    current_password: str = Field(min_length=1, max_length=128)
    security_questions: list[SecurityQuestionResponse] = Field(min_length=3, max_length=3)


class UserResponse(BaseModel):
    user_id: str
    role: str


class AccountStatusResponse(BaseModel):
    status: str
    message: str | None = None


def _raise_password_failure(status_code: int, detail: str) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


def _validate_security_questions(responses: list[SecurityQuestionResponse]) -> None:
    questions = [" ".join(response.question.split()) for response in responses]
    if any(len(question) < 5 for question in questions):
        raise HTTPException(
            status_code=400,
            detail="Each security question must contain at least five characters.",
        )
    if len({question.casefold() for question in questions}) != 3:
        raise HTTPException(status_code=400, detail="Choose three different security questions.")
    if any(len(normalize_security_answer(response.answer)) < 2 for response in responses):
        raise HTTPException(status_code=400, detail="Each security answer must contain at least two characters.")


def _replace_security_answers(
    db: Session, user: User, responses: list[SecurityQuestionResponse]
) -> None:
    _validate_security_questions(responses)
    db.query(SecurityAnswer).filter(SecurityAnswer.user_id == user.id).delete(
        synchronize_session=False
    )
    for position, response in enumerate(responses, start=1):
        db.add(SecurityAnswer(
            user_id=user.id,
            position=position,
            question=" ".join(response.question.split()),
            answer_hash=hash_security_answer(response.answer),
        ))


@router.get("/configuration")
def authentication_configuration(db: Session = Depends(get_db)):
    """Public rules needed by registration and password recovery screens."""
    return {
        "password_policy": password_policy(db),
        "security_questions": settings.security_question_options,
        "required_security_questions": 3,
        "allow_custom_security_questions": True,
    }


def _set_session_cookie(
    response: Response,
    raw_token: str,
    cookie_name: str,
    role: str,
) -> None:
    response.set_cookie(
        key=cookie_name,
        value=raw_token,
        max_age=session_timeout_minutes(role) * 60,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )


@router.post("/login", response_model=UserResponse)
def login(
    credentials: Credentials,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    request.state.audit_user_id = credentials.user_id
    request.state.audit_resource_id = f"user:{credentials.user_id}"
    from app.auth import authenticate_user
    user = authenticate_user(db, credentials.user_id, credentials.password)
    raw_token, _ = create_session(db, user)
    _set_session_cookie(response, raw_token, SESSION_COOKIE, user.role)
    return UserResponse(user_id=user.user_id, role=user.role)


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    request: RegisterRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    http_request.state.audit_user_id = request.user_id
    http_request.state.audit_resource_id = f"user:{request.user_id}"
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    try:
        validate_password_strength(request.password, request.user_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    existing = db.query(User).filter(func.lower(User.user_id) == request.user_id.casefold()).first()
    if existing:
        raise HTTPException(status_code=409, detail="That user ID is already registered.")

    user = User(
        user_id=request.user_id,
        password_hash=hash_password(request.password),
        role=request.role,
        is_approved=False,
    )
    try:
        db.add(user)
        db.flush()
        _replace_security_answers(db, user, request.security_questions)
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "That user ID is already registered.") from exc
    return UserResponse(user_id=user.user_id, role=user.role)


@router.post("/account-status", response_model=AccountStatusResponse)
def account_status(data: UserIdRequest, request: Request, db: Session = Depends(get_db)):
    """Allow the sign-in screen to identify accounts waiting for approval."""
    request.state.audit_user_id = data.user_id
    request.state.audit_resource_id = f"user:{data.user_id}"
    user = db.query(User).filter(User.user_id == data.user_id).first()
    if user and user.is_active and not user.is_approved:
        return AccountStatusResponse(
            status="pending",
            message="Your account is in the admin queue for approval.",
        )
    return AccountStatusResponse(status="not_pending")


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse(user_id=current_user.user_id, role=current_user.role)


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    request.state.audit_resource_id = f"user:{current_user.user_id}"
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        _raise_password_failure(401, "Your session is invalid.")
    if not verify_password(data.current_password, current_user.password_hash):
        _raise_password_failure(400, "Current password is incorrect.")
    if data.new_password != data.confirm_password:
        _raise_password_failure(400, "New passwords do not match.")
    if verify_password(data.new_password, current_user.password_hash):
        _raise_password_failure(400, "New password must be different.")
    try:
        validate_password_strength(data.new_password, current_user.user_id, db)
    except ValueError as exc:
        _raise_password_failure(400, str(exc))

    current_user.password_hash = hash_password(data.new_password)
    current_user.credential_version += 1
    current_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
    db.query(AuthSession).filter(
        AuthSession.user_id == current_user.id,
        AuthSession.token_hash != current_hash,
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": "Password changed successfully."}


@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    request.state.audit_user_id = data.user_id
    request.state.audit_resource_id = f"user:{data.user_id}"
    user = db.query(User).filter(User.user_id == data.user_id).first()
    if not user or not user.is_active or not user.is_approved:
        _raise_password_failure(404, "User ID was not found.")
    stored_answers = (
        db.query(SecurityAnswer)
        .filter(SecurityAnswer.user_id == user.id)
        .order_by(SecurityAnswer.position)
        .all()
    )
    submitted = {item.question: item.answer for item in data.security_questions}
    answers_match = len(stored_answers) == 3 and len(submitted) == 3
    for stored in stored_answers:
        candidate = submitted.get(stored.question, "")
        answers_match = verify_security_answer(candidate, stored.answer_hash) and answers_match
    if not answers_match:
        _raise_password_failure(400, "One or more security answers are incorrect.")
    if data.new_password != data.confirm_password:
        _raise_password_failure(400, "New passwords do not match.")
    if verify_password(data.new_password, user.password_hash):
        _raise_password_failure(400, "New password must be different.")
    try:
        validate_password_strength(data.new_password, user.user_id, db)
    except ValueError as exc:
        _raise_password_failure(400, str(exc))

    user.password_hash = hash_password(data.new_password)
    user.credential_version += 1
    user.failed_login_attempts = 0
    user.is_locked = False
    user.locked_at = None
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(
        synchronize_session=False
    )
    db.commit()
    return {"message": "Password reset successfully. You can now sign in."}


@router.post("/reset-password/questions")
def reset_password_questions(
    data: UserIdRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    request.state.audit_user_id = data.user_id
    request.state.audit_resource_id = f"user:{data.user_id}"
    user = db.query(User).filter(
        User.user_id == data.user_id,
        User.is_active.is_(True),
        User.is_approved.is_(True),
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User ID was not found.")
    questions = [answer.question for answer in user.security_answers]
    if len(questions) != 3:
        raise HTTPException(
            status_code=409,
            detail="Recovery questions are not configured for this account. Sign in and configure them from your profile.",
        )
    return {"questions": questions}


@router.put("/security-questions")
def configure_security_questions(
    data: ConfigureSecurityQuestionsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    _replace_security_answers(db, current_user, data.security_questions)
    db.commit()
    return {"message": "Security questions updated successfully."}


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        auth_session = (
            db.query(AuthSession).filter(AuthSession.token_hash == token_hash).first()
        )
        if auth_session:
            if auth_session.user:
                request.state.audit_user_id = auth_session.user.user_id
                request.state.audit_resource_id = f"user:{auth_session.user.user_id}"
            db.delete(auth_session)
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return Response(status_code=204, headers=response.headers)
