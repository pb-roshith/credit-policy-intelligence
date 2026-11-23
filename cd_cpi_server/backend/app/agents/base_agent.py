"""
Base Section Agent — lightweight wrapper for section-specific agents.

With the Mistral Library + Agents architecture, the actual generation is
handled by MistralLibraryService. This class just holds section metadata
and provides the instructions via the centralized instructions file.
"""

from __future__ import annotations

from app.agents.instructions import get_instructions


class BaseSectionAgent:
    """
    Base class for all section-specific narrative agents.

    Subclasses must set:
        section_key: str  — e.g. "executive_summary"

    The system_prompt is now loaded from app.agents.instructions
    for easy centralized editing.
    """

    section_key: str = ""

    def get_instructions(self) -> str:
        """Get the full agent instructions for this section type."""
        return get_instructions(self.section_key)
