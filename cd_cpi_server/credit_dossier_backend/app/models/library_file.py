"""
LibraryFile model — tracks files uploaded to a deal's Mistral Library.

Each file is uploaded via Mistral Files API and added to the deal's Library.
This table keeps a local reference for the UI and cleanup on deletion.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LibraryFile(Base):
    """A file uploaded to a deal's Mistral Library."""

    __tablename__ = "library_files"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True,
        default=lambda: "lf_" + uuid.uuid4().hex[:8],
    )
    deal_id: Mapped[str] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False,
    )
    mistral_file_id: Mapped[str] = mapped_column(String(256), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # file | url | text
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now,
    )

    # Relationships
    deal: Mapped["Deal"] = relationship(back_populates="library_files")  # type: ignore[name-defined]
