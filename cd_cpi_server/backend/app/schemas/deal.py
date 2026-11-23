"""
Pydantic schemas for Deal, Section, AuditEntry, and Version.
"""

import json
import unicodedata
from datetime import date, datetime
from typing import Optional
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from app.schemas.input_validation import StrictInputModel, validate_markdown_text


def _sanitize_failure_metadata(value):
    """Remove legacy exception text before persisted JSON reaches API clients."""
    if isinstance(value, list):
        return [_sanitize_failure_metadata(item) for item in value]
    if not isinstance(value, dict):
        return value
    sanitized = {}
    for key, item in value.items():
        normalized_key = str(key).casefold()
        if normalized_key in {"error", "exception", "traceback", "stack", "stack_trace"}:
            sanitized[key] = "The operation was unavailable." if item else item
        elif normalized_key == "summary" and isinstance(item, str) and "error" in item.casefold():
            sanitized[key] = "The assessment was unavailable."
        else:
            sanitized[key] = _sanitize_failure_metadata(item)
    return sanitized


# ── Upload (nested — legacy) ───────────────────────────────────
class UploadBrief(BaseModel):
    id: str
    source_type: str
    filename: Optional[str] = None
    url: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Deal Document (new deal-level docs) ────────────────────────
class DealDocumentResponse(BaseModel):
    id: str
    source_type: str
    filename: Optional[str] = None
    url: Optional[str] = None
    note: Optional[str] = None
    extraction_method: Optional[str] = None
    page_count: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SectionDocumentLinkResponse(BaseModel):
    id: str
    document: DealDocumentResponse
    created_at: datetime

    model_config = {"from_attributes": True}


class LinkDocumentsRequest(StrictInputModel):
    document_ids: list[str] = Field(min_length=1, max_length=100)


# ── Library File (Mistral Library) ─────────────────────────────
class LibraryFileResponse(BaseModel):
    id: str
    mistral_file_id: str
    filename: str
    source_type: str
    file_size: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Library Sync Log ───────────────────────────────────────────
class LibrarySyncLogResponse(BaseModel):
    id: str
    doc_title: str
    doc_url: Optional[str] = None
    status: str
    error: Optional[str] = None
    file_size: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Section ─────────────────────────────────────────────────────
class SectionResponse(BaseModel):
    id: str
    section_key: str
    title: str
    description: str
    sources: str
    expected_output: str
    optional: bool
    state: str
    order_index: int
    generated_content: Optional[str] = None
    original_generated_content: Optional[str] = None
    final_generated_content: Optional[str] = None
    custom_instructions: Optional[str] = None
    accuracy_score: Optional[float] = None
    accuracy_details: Optional[dict] = None
    output_template: Optional[str] = None
    template_file_path: Optional[str] = None
    orchestration_strategy: Optional[str] = None
    moderation_status: Optional[str] = None
    moderation_details: Optional[dict] = None
    observability_details: Optional[dict] = None
    source_urls: list[str] = []
    url_scrape_details: Optional[list[dict]] = None
    uploads: list[UploadBrief] = []  # Legacy
    document_links: list[SectionDocumentLinkResponse] = []  # New

    model_config = {"from_attributes": True}

    @field_validator("accuracy_details", "moderation_details", "observability_details", mode="before")
    @classmethod
    def parse_json_details(cls, v):
        """Parse JSON string fields (DB storage) to dict."""
        if isinstance(v, str):
            try:
                return _sanitize_failure_metadata(json.loads(v))
            except (json.JSONDecodeError, TypeError):
                return None
        return _sanitize_failure_metadata(v)

    @field_validator("source_urls", "url_scrape_details", mode="before")
    @classmethod
    def parse_json_lists(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return _sanitize_failure_metadata(parsed) if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return _sanitize_failure_metadata(v or [])


class SectionUpdate(StrictInputModel):
    sources: Optional[str] = Field(default=None, max_length=20_000)
    expected_output: Optional[str] = Field(default=None, max_length=20_000)
    custom_instructions: Optional[str] = Field(default=None, max_length=50_000)
    output_template: Optional[str] = Field(default=None, max_length=100_000)
    generated_content: Optional[str] = Field(default=None, max_length=500_000)
    state: Optional[str] = Field(default=None, pattern=r"^(pending|ready)$")
    source_urls: Optional[list[str]] = None

    @field_validator("sources", "expected_output", "custom_instructions", "output_template", "generated_content")
    @classmethod
    def validate_section_text(cls, value):
        return validate_markdown_text(value)

    @field_validator("source_urls")
    @classmethod
    def validate_source_urls(cls, value):
        if value is None:
            return value
        if len(value) > 10:
            raise ValueError("A section can contain at most 10 URLs.")
        normalized: list[str] = []
        for raw_url in value:
            if any(char.isspace() or ord(char) < 32 or char in '<>"\'\\' for char in raw_url):
                raise ValueError("URLs must not contain whitespace, markup, or control characters.")
            url = raw_url.strip()
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(f"Invalid HTTP/HTTPS URL: {raw_url}")
            if len(url) > 2048:
                raise ValueError("A URL cannot exceed 2048 characters.")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("URLs must not contain credentials.")
            try:
                parsed.port
            except ValueError as exc:
                raise ValueError("URL port is invalid.") from exc
            if url not in normalized:
                normalized.append(url)
        return normalized


# ── Audit Entry ─────────────────────────────────────────────────
class AuditEntryResponse(BaseModel):
    id: str
    action: str
    subject: str
    user: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Version ─────────────────────────────────────────────────────
class VersionCreate(StrictInputModel):
    notes: str = Field(default="", max_length=4000)

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value):
        return validate_markdown_text(value)


class VersionReviewRequest(StrictInputModel):
    comments: str = Field(default="", max_length=4000)

    @field_validator("comments")
    @classmethod
    def validate_comments(cls, value):
        return validate_markdown_text(value)


class VersionResponse(BaseModel):
    id: str
    notes: str
    status: str
    review_comments: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NarrativeVersionResponse(BaseModel):
    id: str
    deal_id: str
    section_id: str
    content: str
    version_type: str
    parent_version_id: Optional[str] = None
    created_by: str
    is_final: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NarrativeEditLockResponse(BaseModel):
    section_id: str
    locked_by: str
    expires_at: datetime


# ── Deal ────────────────────────────────────────────────────────
class DealInput(StrictInputModel):
    @field_validator("customer", "customer_type", "industry", "segment", "facility",
                     "pricing", "repayment", "status", check_fields=False)
    @classmethod
    def validate_plain_text(cls, value: Optional[str], info: ValidationInfo) -> Optional[str]:
        if value is None:
            return value
        if any(
            unicodedata.category(char)[0] not in {"L", "M", "N"}
            and char not in " .,'’\"()-/&+:%=$€£₹#@!?;[]"
            for char in value
        ):
            raise ValueError(f"{info.field_name} must contain plain text, without markup or control characters.")
        value = value.strip()
        if info.field_name == "customer" and not value:
            raise ValueError("Customer name must not be blank.")
        return value

    @field_validator("due", check_fields=False)
    @classmethod
    def validate_due(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return value
        if len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError("Target completion date must use YYYY-MM-DD.")
        return value

    @field_validator("theme_palette", check_fields=False)
    @classmethod
    def validate_palette(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        import re
        try:
            colors = json.loads(value)
        except ValueError as exc:
            raise ValueError("Theme palette must be a JSON array of hex colors.") from exc
        if not isinstance(colors, list) or not colors or any(
            not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color)
            for color in colors
        ):
            raise ValueError("Theme palette must be a JSON array of hex colors.")
        return value

    @field_validator("geography", check_fields=False)
    @classmethod
    def validate_geography(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if any(
            unicodedata.category(char)[0] not in {"L", "M", "N"}
            and char not in " .,'’()-/&"
            for char in value
        ):
            raise ValueError("Geography must contain a location name, without markup or control characters.")
        return value


class DealCreate(DealInput):
    creation_request_id: Optional[str] = Field(default=None, min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    rating: str = Field(default="BB", min_length=1, max_length=12)
    collateral_coverage: float = Field(default=100, ge=0, le=500, allow_inf_nan=False)
    total_required_documents: int = Field(default=1, ge=1, le=1000)
    uploaded_required_documents: int = Field(default=0, ge=0, le=1000)

    @model_validator(mode="after")
    def validate_document_counts(self):
        if self.uploaded_required_documents > self.total_required_documents:
            raise ValueError("Supplied documents cannot exceed required documents.")
        return self

    customer: str = Field(..., min_length=1, max_length=256)
    customer_type: str = Field(default="Existing", max_length=32)
    industry: str = Field(default="", max_length=128)
    segment: str = Field(default="Mid Corporate", max_length=64)
    geography: str = Field(default="", max_length=128)
    kyc: str = Field(default="pending", pattern=r"^(pending|verified)$")
    facility: str = Field(default="Term Loan", max_length=64)
    currency: str = Field(default="INR", min_length=3, max_length=8, pattern=r"^[A-Z]+$")
    amount: float = Field(gt=0, le=1_000_000_000_000_000, allow_inf_nan=False)
    tenure: int = Field(default=60, ge=1, le=1200)
    pricing: str = Field(default="", max_length=128)
    repayment: str = Field(default="", max_length=128)
    collateral: bool = False
    due: str = Field(default="", max_length=16)


class DealSearchRequest(StrictInputModel):
    """Filters sent in a POST body so customer searches never enter URLs/logs."""
    status: Optional[str] = Field(default=None, max_length=32)
    search: Optional[str] = Field(default=None, max_length=256)


class DealUpdate(DealInput):
    customer: Optional[str] = Field(default=None, min_length=1, max_length=256)
    customer_type: Optional[str] = Field(default=None, max_length=32)
    industry: Optional[str] = Field(default=None, max_length=128)
    segment: Optional[str] = Field(default=None, max_length=64)
    geography: Optional[str] = Field(default=None, max_length=128)
    kyc: Optional[str] = Field(default=None, pattern=r"^(pending|verified)$")
    facility: Optional[str] = Field(default=None, max_length=64)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8, pattern=r"^[A-Z]+$")
    amount: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    tenure: Optional[int] = Field(default=None, ge=0, le=1200)
    pricing: Optional[str] = Field(default=None, max_length=128)
    repayment: Optional[str] = Field(default=None, max_length=128)
    collateral: Optional[bool] = None
    due: Optional[str] = Field(default=None, max_length=16)
    status: Optional[str] = Field(default=None, max_length=32)
    primary_color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    theme_palette: Optional[str] = Field(default=None, max_length=256)


class DealResponse(BaseModel):
    intake: Optional[dict] = None

    @field_validator("intake")
    @classmethod
    def public_intake(cls, value):
        return {key: item for key, item in value.items() if key != "input_hash"} if value else value
    id: str
    customer: str
    customer_type: str
    industry: str
    segment: str
    geography: str
    city: str
    sector: str
    kyc: str
    facility: str
    currency: str
    amount: float
    tenure: int
    pricing: str
    repayment: str
    collateral: bool
    due: str
    owner: str
    status: str
    created_at: datetime
    updated_at: datetime
    mistral_library_id: Optional[str] = None
    company_mistral_library_id: Optional[str] = None
    company_document_count: int = 0
    library_sync_status: str
    primary_color: str
    secondary_color: str
    theme_palette: list[str] = []

    sections: list[SectionResponse] = []
    documents: list[DealDocumentResponse] = []  # Deal-level documents (legacy)
    library_files: list[LibraryFileResponse] = []  # Mistral Library files
    sync_logs: list[LibrarySyncLogResponse] = []
    audit_entries: list[AuditEntryResponse] = []
    versions: list[VersionResponse] = []

    model_config = {"from_attributes": True}

    @field_validator("theme_palette", mode="before")
    @classmethod
    def parse_theme_palette(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return ["#002060", "#800020"]
        return v or ["#002060", "#800020"]


class DealListResponse(BaseModel):
    """Lighter response for the pipeline table — excludes full section content."""
    id: str
    customer: str
    customer_type: str
    industry: str
    segment: str
    geography: str
    city: str
    sector: str
    kyc: str
    facility: str
    currency: str
    amount: float
    tenure: int
    pricing: str
    repayment: str
    collateral: bool
    due: str
    owner: str
    status: str
    library_sync_status: str = "not_started"
    created_at: datetime
    updated_at: datetime
    sections_ready: int = 0
    sections_total: int = 0
    versions_count: int = 0

    model_config = {"from_attributes": True}
