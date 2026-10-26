"""
LibrarySyncLog — tracks per-document sync status for the MCP → Library pipeline.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, audit_table_args


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LibrarySyncLog(Base):
    __tablename__ = "library_sync_logs"
    __table_args__ = audit_table_args()

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True,
        default=lambda: "sync_" + uuid.uuid4().hex[:8],
    )
    deal_id: Mapped[str] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False,
    )
    doc_title: Mapped[str] = mapped_column(String(512), nullable=False)
    doc_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued",
    )
    # "queued" → "downloading" → "uploading" → "completed" → "failed" → "skipped"
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    deal: Mapped["Deal"] = relationship(back_populates="sync_logs")  # type: ignore[name-defined]
