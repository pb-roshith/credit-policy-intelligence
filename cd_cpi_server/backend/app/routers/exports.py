"""
Exports API router — generate and download PPT, PDF, DOCX documents.
Also provides the combined report generation endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.database import get_db
from app.auth import get_current_user, require_deal_owner
from app.services.export_service import ExportService
from app.models.deal import AuditEntry
from app.models.user import User
from app.report_security import safe_export_filename, secure_download_headers

router = APIRouter(prefix="/api/deals/{deal_id}", tags=["exports"], dependencies=[Depends(require_deal_owner)])


FORMAT_CONFIG = {
    "pdf": {
        "method": ExportService.generate_pdf,
        "content_type": "application/pdf",
        "extension": "pdf",
    },
    "docx": {
        "method": ExportService.generate_docx,
        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "extension": "docx",
    },
    "pptx": {
        "method": ExportService.generate_pptx,
        "content_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "extension": "pptx",
    },
}


import inspect

@router.post("/export/{format}")
async def export_deal(
    deal_id: str,
    format: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Export the deal as PPT, PDF, or DOCX.
    Returns a downloadable file.
    """
    format = format.lower()
    if format == "ppt":
        format = "pptx"

    if format not in FORMAT_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}. Use pdf, docx, or pptx.")

    deal = ExportService.get_deal_with_sections(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    config = FORMAT_CONFIG[format]
    if inspect.iscoroutinefunction(config["method"]):
        file_bytes = await config["method"](deal)
    else:
        file_bytes = config["method"](deal)

    # Audit entry
    audit = AuditEntry(
        deal_id=deal_id,
        action=f"export.{format}",
        subject=deal.customer,
        user=current_user.user_id,
    )
    db.add(audit)

    # Update status to Exported if approved
    if deal.status == "Approved":
        deal.status = "Exported"

    db.commit()

    filename = safe_export_filename(deal.customer, "PitchBook", config["extension"])

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=config["content_type"],
        headers=secure_download_headers(filename),
    )


@router.post("/report")
def generate_combined_report(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a combined PDF report from all sections.
    This is the final, complete credit pitch book.
    """
    deal = ExportService.get_deal_with_sections(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    pdf_bytes = ExportService.generate_combined_report(deal)

    # Audit entry
    audit = AuditEntry(
        deal_id=deal_id,
        action="report.generated",
        subject=f"Combined report for {deal.customer}",
        user=current_user.user_id,
    )
    db.add(audit)
    db.commit()

    filename = safe_export_filename(deal.customer, "CreditReport", "pdf")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers=secure_download_headers(filename),
    )
