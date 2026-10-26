"""
Documents API router — deal-level document management and section linking.

Documents are uploaded once at the deal level (processed via Mistral OCR),
then linked to one or more sections via a multi-select picker.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.deal import Deal, Section
from app.models.document import DealDocument, SectionDocumentLink
from app.schemas.deal import (
    DealDocumentResponse,
    SectionDocumentLinkResponse,
    LinkDocumentsRequest,
)
from app.services.ingestion_service import IngestionService
from app.services.deal_service import DealService
from app.auth import require_deal_owner
from app.file_validation import UploadValidationError, validate_uploaded_file

router = APIRouter(prefix="/api/deals/{deal_id}", tags=["documents"], dependencies=[Depends(require_deal_owner)])


# ── Deal-Level Document Management ─────────────────────────────


@router.get("/documents", response_model=list[DealDocumentResponse])
def list_deal_documents(deal_id: str, db: Session = Depends(get_db)):
    """List all documents uploaded to this deal."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    docs = (
        db.query(DealDocument)
        .filter(DealDocument.deal_id == deal_id)
        .order_by(DealDocument.created_at)
        .all()
    )
    return docs


@router.post(
    "/documents",
    response_model=DealDocumentResponse,
    status_code=201,
)
async def upload_deal_document(
    deal_id: str,
    source_type: Literal["file", "url", "text"] = Form(...),
    file: UploadFile | None = File(None),
    url: str | None = Form(None, max_length=2048),
    text_content: str | None = Form(None, max_length=500_000),
    note: str | None = Form(None, max_length=4000),
    db: Session = Depends(get_db),
):
    """
    Upload a document to the deal's document library.

    - source_type='file': Upload a file (PDF, DOCX, XLSX, etc.)
      → Processed via Mistral OCR for high-accuracy extraction.
    - source_type='url': Provide a URL to fetch content from.
    - source_type='text': Paste text directly.

    Duplicate files (same SHA-256 hash) are detected and reused
    without re-processing.
    """
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

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
        doc = await IngestionService.process_deal_document(
            db=db,
            deal_id=deal_id,
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
        doc = await IngestionService.process_url_document(
            db=db, deal_id=deal_id, url=url, note=note
        )
    elif source_type == "text":
        if not text_content:
            raise HTTPException(
                status_code=400,
                detail="text_content is required for source_type='text'",
            )
        doc = await IngestionService.process_text_document(
            db=db, deal_id=deal_id, text_content=text_content, note=note
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="source_type must be 'file', 'url', or 'text'",
        )

    return doc


@router.delete("/documents/{document_id}", status_code=204)
def delete_deal_document(
    deal_id: str,
    document_id: str,
    db: Session = Depends(get_db),
):
    """Delete a document from the deal library (and all section links)."""
    document = db.query(DealDocument).filter(
        DealDocument.id == document_id,
        DealDocument.deal_id == deal_id,
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if not IngestionService.delete_deal_document(db, document_id):
        raise HTTPException(status_code=404, detail="Document not found")


# ── Section Document Linking ───────────────────────────────────


@router.post(
    "/sections/{section_id}/documents/link",
    response_model=list[SectionDocumentLinkResponse],
)
def link_documents_to_section(
    deal_id: str,
    section_id: str,
    body: LinkDocumentsRequest,
    db: Session = Depends(get_db),
):
    """
    Link existing deal documents to a section.
    Accepts a list of document IDs. Idempotent — already-linked documents
    are returned without creating duplicates.
    """
    section = db.query(Section).filter(
        Section.id == section_id,
        Section.deal_id == deal_id,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # Verify all document IDs belong to this deal
    for doc_id in body.document_ids:
        doc = (
            db.query(DealDocument)
            .filter(
                DealDocument.id == doc_id,
                DealDocument.deal_id == deal_id,
            )
            .first()
        )
        if not doc:
            raise HTTPException(
                status_code=404,
                detail=f"Document {doc_id} not found in deal {deal_id}",
            )

    links = IngestionService.link_documents_to_section(
        db, section_id, body.document_ids
    )
    return links


@router.delete(
    "/sections/{section_id}/documents/{document_id}/unlink",
    status_code=204,
)
def unlink_document_from_section(
    deal_id: str,
    section_id: str,
    document_id: str,
    db: Session = Depends(get_db),
):
    """Remove a document link from a section (does not delete the document)."""
    section = db.query(Section).filter(
        Section.id == section_id,
        Section.deal_id == deal_id,
    ).first()
    document = db.query(DealDocument).filter(
        DealDocument.id == document_id,
        DealDocument.deal_id == deal_id,
    ).first()
    if not section or not document:
        raise HTTPException(status_code=404, detail="Document link not found")
    if not IngestionService.unlink_document_from_section(
        db, section_id, document_id
    ):
        raise HTTPException(
            status_code=404, detail="Document link not found"
        )


@router.get(
    "/sections/{section_id}/documents",
    response_model=list[SectionDocumentLinkResponse],
)
def list_section_documents(
    deal_id: str,
    section_id: str,
    db: Session = Depends(get_db),
):
    """List all documents linked to a specific section."""
    section = db.query(Section).filter(
        Section.id == section_id,
        Section.deal_id == deal_id,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    links = (
        db.query(SectionDocumentLink)
        .options(joinedload(SectionDocumentLink.document))
        .filter(SectionDocumentLink.section_id == section_id)
        .all()
    )
    return links
