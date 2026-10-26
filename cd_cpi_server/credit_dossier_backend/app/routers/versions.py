"""Versions API router — submit, review, and download frozen versions."""

import io
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import (
    require_credit_analyst,
    require_deal_owner,
    require_relationship_manager,
)
from app.models.deal import Version
from app.models.narrative_version import NarrativeVersion
from app.models.user import User
from app.schemas.deal import VersionCreate, VersionResponse, VersionReviewRequest
from app.services.deal_service import DealService
from app.services.export_service import ExportService
from app.report_security import safe_export_filename, secure_download_headers

router = APIRouter(prefix="/api/deals/{deal_id}/versions", tags=["versions"], dependencies=[Depends(require_deal_owner)])


@router.post("", response_model=VersionResponse, status_code=201)
def submit_version(
    deal_id: str,
    data: VersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_relationship_manager),
):
    """Submit current draft as a frozen version for review."""
    version = DealService.create_version(db, deal_id, data.notes, current_user.user_id)
    if not version:
        raise HTTPException(status_code=404, detail="Deal not found")
    return version


@router.patch("/{version_id}/approve", response_model=VersionResponse)
def approve_version(
    deal_id: str,
    version_id: str,
    data: VersionReviewRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_credit_analyst),
):
    """Approve a submitted version. Changes deal status to Approved."""
    version = DealService.approve_version(
        db,
        deal_id,
        version_id,
        current_user.user_id,
        data.comments if data else "",
    )
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


@router.post("/{version_id}/download")
def download_version(
    deal_id: str,
    version_id: str,
    db: Session = Depends(get_db),
):
    """Download the immutable submitted version as a PDF."""
    version = db.query(Version).filter(
        Version.id == version_id,
        Version.deal_id == deal_id,
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    deal = ExportService.get_deal_with_sections(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    try:
        if version.snapshot_json:
            snapshot = json.loads(version.snapshot_json)
            for field, value in snapshot["deal"].items():
                setattr(deal, field, value)
            sections_by_id = {section.id: section for section in deal.sections}
            frozen_sections = []
            for frozen in snapshot["sections"]:
                section = sections_by_id.get(frozen["id"])
                if section is None:
                    continue
                for field in ("title", "state", "order_index"):
                    setattr(section, field, frozen.get(field))
                frozen_content = (
                    frozen.get("generated_content")
                    or frozen.get("final_generated_content")
                )
                section.generated_content = frozen_content
                section.final_generated_content = frozen_content
                frozen_sections.append(section)
            deal.sections = frozen_sections
        else:
            # Rebuild versions created before deal snapshots were introduced
            # from each section's most recent narrative at submission time.
            historical_versions = (
                db.query(NarrativeVersion)
                .filter(
                    NarrativeVersion.deal_id == deal_id,
                    NarrativeVersion.created_at <= version.created_at,
                )
                .order_by(
                    NarrativeVersion.created_at.asc(),
                    NarrativeVersion.id.asc(),
                )
                .all()
            )
            content_by_section = {
                historical.section_id: historical.content
                for historical in historical_versions
            }
            for section in deal.sections:
                historical_content = content_by_section.get(section.id)
                if historical_content is not None:
                    section.generated_content = historical_content
                    section.final_generated_content = historical_content
                    section.state = "ready"
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Version snapshot is invalid") from exc

    file_bytes = ExportService.generate_pdf(deal)
    filename = safe_export_filename(deal.customer, version.id, "pdf")
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/pdf",
        headers=secure_download_headers(filename),
    )


@router.patch("/{version_id}/deny", response_model=VersionResponse)
def deny_version(
    deal_id: str,
    version_id: str,
    data: VersionReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_credit_analyst),
):
    """Deny a submitted version and return review comments to the RM."""
    comments = data.comments.strip()
    if not comments:
        raise HTTPException(
            status_code=400,
            detail="Review comments are required when denying a version.",
        )
    version = DealService.deny_version(
        db, deal_id, version_id, current_user.user_id, comments
    )
    if not version:
        raise HTTPException(
            status_code=404,
            detail="Submitted version not found.",
        )
    return version
