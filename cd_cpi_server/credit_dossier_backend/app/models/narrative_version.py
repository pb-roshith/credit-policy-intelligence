"""Per-section generated and edited narrative history."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NarrativeVersion(Base):
    __tablename__ = "narrative_versions"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: "nv_" + uuid.uuid4().hex[:10],
    )
    deal_id: Mapped[str] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[str] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="generated",
    )
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("narrative_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="Analyst",
    )
    is_final: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        index=True,
    )
