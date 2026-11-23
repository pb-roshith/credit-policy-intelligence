"""
Upload model — represents files, URLs, or text pasted as grounding inputs for sections.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: "upl_" + uuid.uuid4().hex[:8])
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)

    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # file | url | text
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Extracted text for RAG
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Mistral Document Library tracking
    mistral_document_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Use string reference to avoid circular import
    section: Mapped["Section"] = relationship(back_populates="uploads")  # type: ignore[name-defined]
