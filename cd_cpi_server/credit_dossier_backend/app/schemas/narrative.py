"""
Pydantic schemas for AI narrative generation.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator

from app.schemas.input_validation import StrictInputModel, validate_markdown_text


class NarrativeRequest(StrictInputModel):
    custom_instructions: Optional[str] = Field(default=None, max_length=50_000)

    @field_validator("custom_instructions")
    @classmethod
    def validate_instructions(cls, value):
        return validate_markdown_text(value)


class NarrativeResponse(BaseModel):
    section_id: str
    section_key: str
    title: str
    generated_content: str
    state: str
    accuracy_score: Optional[float] = None
    accuracy_details: Optional[dict] = None
    orchestration_strategy: Optional[str] = None
    timing: Optional[dict] = None


class DraftAllResponse(BaseModel):
    """Response when all sections are drafted in parallel."""
    results: list[NarrativeResponse]
    total: int
    succeeded: int
    failed: int


class DraftSectionProgress(BaseModel):
    section_id: str
    title: str
    status: str
    stage: str


class DraftAllJobResponse(BaseModel):
    job_id: str
    deal_id: str
    status: str
    percent: int
    completed: int
    failed: int
    total: int
    sections: list[DraftSectionProgress]
    error: Optional[str] = None

