"""
Pydantic schemas for file uploads.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UploadResponse(BaseModel):
    id: str
    source_type: str
    filename: Optional[str] = None
    file_path: Optional[str] = None
    url: Optional[str] = None
    text_content: Optional[str] = None
    note: Optional[str] = None
    extracted_text: Optional[str] = None
    mistral_document_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
