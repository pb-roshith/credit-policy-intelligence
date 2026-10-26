"""
DealDocument & SectionDocumentLink models.

DealDocument: A document uploaded once at the deal level, processed once via
Mistral OCR. Reusable across multiple sections without re-processing.

SectionDocumentLink: Many-to-many junction linking documents to sections.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, Text, DateTime, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DealDocument(Base):
    """A document uploaded to a deal. Processed once, reusable across sections."""

    __tablename__ = "deal_documents"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True,
        default=lambda: "doc_" + uuid.uuid4().hex[:8],
    )
    deal_id: Mapped[str] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False,
    )

    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # file | url | text
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA-256
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # OCR-extracted content — the gold, processed once
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
    )  # mistral_ocr | local_fallback | plain_text
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now,
    )

    # Relationships
    deal: Mapped["Deal"] = relationship(back_populates="documents")  # type: ignore[name-defined]
    section_links: Mapped[list["SectionDocumentLink"]] = relationship(
        back_populates="document", cascade="all, delete-orphan",
    )


class SectionDocumentLink(Base):
    """Links a deal document to a section (many-to-many junction)."""

    __tablename__ = "section_document_links"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True,
        default=lambda: "sdl_" + uuid.uuid4().hex[:8],
    )
    section_id: Mapped[str] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("deal_documents.id", ondelete="CASCADE"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now,
    )

    __table_args__ = (
        UniqueConstraint("section_id", "document_id", name="uq_section_document"),
    )

    # Relationships
    section: Mapped["Section"] = relationship(back_populates="document_links")  # type: ignore[name-defined]
    document: Mapped["DealDocument"] = relationship(back_populates="section_links")
