"""Application users and server-side login sessions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, audit_table_args


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="credit_analyst"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    identity_source: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    security_answers: Mapped[list["SecurityAnswer"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="SecurityAnswer.position"
    )


class SecurityAnswer(Base):
    __tablename__ = "security_answers"
    __table_args__ = (
        UniqueConstraint("user_id", "position", name="uq_security_answer_position"),
        UniqueConstraint("user_id", "question", name="uq_security_answer_question"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(nullable=False)
    question: Mapped[str] = mapped_column(String(256), nullable=False)
    answer_hash: Mapped[str] = mapped_column(String(256), nullable=False)

    user: Mapped[User] = relationship(back_populates="security_answers")


class PasswordPolicyConfiguration(Base):
    """Database-backed policy editable by administrators."""

    __tablename__ = "password_policy_configuration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    min_length: Mapped[int] = mapped_column(Integer, nullable=False)
    max_length: Mapped[int] = mapped_column(Integer, nullable=False)
    min_uppercase: Mapped[int] = mapped_column(Integer, nullable=False)
    min_lowercase: Mapped[int] = mapped_column(Integer, nullable=False)
    min_digits: Mapped[int] = mapped_column(Integer, nullable=False)
    min_special: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class PasswordAuditEvent(Base):
    """Immutable audit record for password changes and resets."""

    __tablename__ = "password_audit_events"
    __table_args__ = audit_table_args()

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


class AuditLog(Base):
    """Administrative-action, user-event, or system-error audit record."""

    __tablename__ = "audit_logs"
    __table_args__ = audit_table_args()

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="sessions")
