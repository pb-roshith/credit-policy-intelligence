"""
Core ORM models: Deal, Section, AuditEntry, Version.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, audit_table_args


def _uuid() -> str:
    return "deal_" + uuid.uuid4().hex[:7]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    customer: Mapped[str] = mapped_column(String(256), nullable=False)
    customer_type: Mapped[str] = mapped_column(String(32), nullable=False, default="Existing")
    industry: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    segment: Mapped[str] = mapped_column(String(64), nullable=False, default="Mid Corporate")
    geography: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    city: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    sector: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    kyc: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    # Facility details
    facility: Mapped[str] = mapped_column(String(64), nullable=False, default="Term Loan")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    tenure: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    pricing: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    repayment: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    collateral: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    due: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    # Canonical intake and hosted-agent provenance shared with CPI.
    intake: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    creation_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Mistral Document Library (managed RAG)
    # Company source library is read-only and shared across the client's deals.
    company_mistral_library_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    company_document_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # Deal library contains only documents uploaded specifically to this deal.
    mistral_library_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    library_sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")


    # Theme
    primary_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#002060")
    secondary_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#800020")
    theme_palette: Mapped[str] = mapped_column(String(256), nullable=False, default='["#002060", "#800020"]')

    # Workflow
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="Analyst")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    sections: Mapped[list["Section"]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", order_by="Section.order_index"
    )
    documents: Mapped[list["DealDocument"]] = relationship(  # type: ignore[name-defined]
        back_populates="deal", cascade="all, delete-orphan", order_by="DealDocument.created_at"
    )
    audit_entries: Mapped[list["AuditEntry"]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", order_by="AuditEntry.created_at"
    )
    versions: Mapped[list["Version"]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", order_by="Version.created_at"
    )

    library_files: Mapped[list["LibraryFile"]] = relationship(  # type: ignore[name-defined]
        back_populates="deal", cascade="all, delete-orphan", order_by="LibraryFile.created_at",
    )
    sync_logs: Mapped[list["LibrarySyncLog"]] = relationship(  # type: ignore[name-defined]
        back_populates="deal", cascade="all, delete-orphan", order_by="LibrarySyncLog.created_at"
    )


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=False)
    section_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sources: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_output: Mapped[str] = mapped_column(Text, nullable=False, default="")
    optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Orchestration Strategy
    orchestration_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI-generated content
    generated_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_generated_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_generated_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    edit_lock_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    edit_lock_user_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    edit_lock_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Accuracy assessment (set after generation)
    accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string

    # Output template — markdown template the AI agent should follow
    output_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Moderation — guardrail status for user-provided inputs
    moderation_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "safe", "flagged", or None
    moderation_details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    observability_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_urls: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    url_scrape_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    deal: Mapped["Deal"] = relationship(back_populates="sections")
    uploads: Mapped[list["Upload"]] = relationship(  # type: ignore[name-defined]
        back_populates="section", cascade="all, delete-orphan"
    )
    document_links: Mapped[list["SectionDocumentLink"]] = relationship(  # type: ignore[name-defined]
        back_populates="section", cascade="all, delete-orphan",
    )


class AuditEntry(Base):
    __tablename__ = "audit_entries"
    __table_args__ = audit_table_args()

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: "a_" + uuid.uuid4().hex[:8])
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    subject: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    user: Mapped[str] = mapped_column(String(128), nullable=False, default="System")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    deal: Mapped["Deal"] = relationship(back_populates="audit_entries")


class Version(Base):
    __tablename__ = "versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: "v_" + uuid.uuid4().hex[:6])
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted")
    review_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    deal: Mapped["Deal"] = relationship(back_populates="versions")
