"""
MistralAgent model — persists Mistral agent IDs per section.

There are 16 global agents (one per section), created via Mistral Agents API.
Agent IDs are stored here for reuse across generation calls for all deals.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MistralAgent(Base):
    """A global Mistral agent created for a specific section."""

    __tablename__ = "mistral_agents"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True,
        default=lambda: "ma_" + uuid.uuid4().hex[:8],
    )
    section_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    agent_id: Mapped[str] = mapped_column(String(256), nullable=False)  # Mistral's agent ID
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now,
    )

