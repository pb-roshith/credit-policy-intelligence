"""
Deal-specific upload library management via Mistral.

Company documents stay in their registered source library. Files handled here
belong only to this deal; generation searches both libraries together.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.deal import Deal
from app.models.library_file import LibraryFile
from app.schemas.deal import LibraryFileResponse
from app.services.mistral_library_service import MistralLibraryService
from app.auth import require_deal_owner
from app.file_validation import UploadValidationError, validate_uploaded_file

import httpx

router = APIRouter(prefix="/api/deals/{deal_id}/library", tags=["library"], dependencies=[Depends(require_deal_owner)])


@router.get("", response_model=list[LibraryFileResponse])
def list_library_files(deal_id: str, db: Session = Depends(get_db)):
    """List all files in the deal's Mistral Library."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    files = (
        db.query(LibraryFile)
        .filter(LibraryFile.deal_id == deal_id)
        .order_by(LibraryFile.created_at)
        .all()
    )
    return files


@router.post("", response_model=LibraryFileResponse, status_code=201)
async def upload_to_library(
    deal_id: str,
    source_type: Literal["file", "url", "text"] = Form(...),
    file: UploadFile | None = File(None),
    url: str | None = Form(None, max_length=2048),
    text_content: str | None = Form(None, max_length=500_000),
    note: str | None = Form(None, max_length=4000),
    db: Session = Depends(get_db),
):
    """
    Upload a document to the deal's Mistral Library.

    - source_type='file': Upload a file (PDF, DOCX, XLSX, etc.)
    - source_type='url': Fetch content from a URL
    - source_type='text': Paste text directly

    Files are uploaded to Mistral's managed library for RAG access
    by all section agents.
    """
    deal = (
        db.query(Deal)
        .options(joinedload(Deal.library_files))
        .filter(Deal.id == deal_id)
        .first()
    )
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # ── Ensure Mistral Library exists BEFORE processing content ──
    if not deal.mistral_library_id:
        library_id = await MistralLibraryService.create_library(db, deal)
        if not library_id:
            raise HTTPException(status_code=502, detail="Unable to initialize the document library.")

    if source_type == "file":
        if not file:
            raise HTTPException(
                status_code=400, detail="File is required for source_type='file'"
            )
        file_bytes = await file.read()
        try:
            filename = validate_uploaded_file(file.filename, file_bytes)
        except UploadValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        lib_file = await MistralLibraryService.upload_file_to_library(
            db=db,
            deal=deal,
            file_bytes=file_bytes,
            filename=filename,
            source_type="file",
            note=note,
        )

    elif source_type == "url":
        if not url:
            raise HTTPException(
                status_code=400, detail="URL is required for source_type='url'"
            )
        # Fetch content from URL
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
            async with httpx.AsyncClient(
                timeout=30.0, follow_redirects=True
            ) as http_client:
                response = await http_client.get(url, headers=headers)
                response.raise_for_status()
                file_bytes = response.content
                filename = url.split("/")[-1] or "downloaded_file.txt"
                content_type = response.headers.get("content-type", "")
                if "text" in content_type or "json" in content_type:
                    if not filename.endswith((".txt", ".json", ".csv", ".md")):
                        filename = filename + ".txt"
        except httpx.HTTPStatusError as e:
            # Fallback: save URL as a text reference so the library still gets content
            import logging
            logging.getLogger(__name__).warning(
                f"URL fetch returned HTTP {e.response.status_code} for {url}, "
                f"saving as text reference"
            )
            file_bytes = (
                f"Source URL: {url}\n\n"
                f"Note: This URL could not be fetched automatically "
                f"(HTTP {e.response.status_code} {e.response.reason_phrase}). "
                f"The content should be reviewed manually.\n"
            ).encode("utf-8")
            filename = "url_reference.txt"
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=400, detail="Failed to fetch the URL. Please verify it and try again."
            ) from e

        lib_file = await MistralLibraryService.upload_file_to_library(
            db=db,
            deal=deal,
            file_bytes=file_bytes,
            filename=filename,
            source_type="url",
            note=note or url,
        )

    elif source_type == "text":
        if not text_content:
            raise HTTPException(
                status_code=400,
                detail="text_content is required for source_type='text'",
            )
        file_bytes = text_content.encode("utf-8")
        filename = "pasted_text.txt"
        lib_file = await MistralLibraryService.upload_file_to_library(
            db=db,
            deal=deal,
            file_bytes=file_bytes,
            filename=filename,
            source_type="text",
            note=note,
        )

    else:
        raise HTTPException(
            status_code=400,
            detail="source_type must be 'file', 'url', or 'text'",
        )

    # ── Sync all agents to this deal's library after upload ──
    return lib_file


@router.delete("/{file_id}", status_code=204)
async def delete_library_file(
    deal_id: str,
    file_id: str,
    db: Session = Depends(get_db),
):
    """Remove a file from the Mistral Library."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    deleted = await MistralLibraryService.delete_library_file(db, deal, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Library file not found")


@router.post("/initialize", status_code=200)
async def initialize_library(
    deal_id: str,
    db: Session = Depends(get_db),
):
    """
    Initialize the Mistral Library + all 16 section agents for a deal.
    Idempotent — safe to call multiple times.
    """
    deal = (
        db.query(Deal)
        .options(joinedload(Deal.sections))
        .filter(Deal.id == deal_id)
        .first()
    )
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Create library
    library_id = await MistralLibraryService.create_library(db, deal)

    # Create all agents
    agents = await MistralLibraryService.create_all_agents(db, deal)

    return {
        "library_id": library_id,
        "agents_created": len(agents),
        "agent_keys": list(agents.keys()),
    }
