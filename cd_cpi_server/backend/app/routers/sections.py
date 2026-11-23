"""
Sections API router — section management, narrative generation, and template management.
"""

import os
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.config import settings
from app.database import SessionLocal, get_db
from app.models.deal import Section
from app.schemas.deal import (
    NarrativeEditLockResponse,
    NarrativeVersionResponse,
    SectionResponse,
    SectionUpdate,
)
from app.schemas.narrative import (
    DraftAllJobResponse,
    DraftAllResponse,
    NarrativeRequest,
    NarrativeResponse,
)
from app.services.deal_service import DealService
from app.services.narrative_service import NarrativeService
from app.services.ingestion_service import extract_text_preview
from app.services.moderation_service import ModerationService
from app.services.narrative_version_service import NarrativeVersionService
from app.auth import get_current_user, require_deal_owner
from app.models.user import User
from app.narrative_lock import NarrativeLockService
from app.file_validation import TEMPLATE_EXTENSIONS, UploadValidationError, validate_uploaded_file

router = APIRouter(prefix="/api/deals/{deal_id}/sections", tags=["sections"], dependencies=[Depends(require_deal_owner)])
_draft_all_jobs: dict[str, dict[str, Any]] = {}
_draft_all_jobs_lock = threading.Lock()


def _get_deal_section(db: Session, deal_id: str, section_id: str):
    return db.query(Section).filter(
        Section.id == section_id,
        Section.deal_id == deal_id,
    ).first()


def _draft_job_snapshot(job_id: str) -> dict[str, Any] | None:
    with _draft_all_jobs_lock:
        job = _draft_all_jobs.get(job_id)
        if not job:
            return None
        sections = [dict(section) for section in job["sections"]]
        finished = sum(
            section["status"] in {"completed", "failed"}
            for section in sections
        )
        snapshot = {**job, "sections": sections}
        snapshot["percent"] = (
            round((finished / len(sections)) * 100) if sections else 100
        )
        snapshot["completed"] = sum(
            section["status"] == "completed" for section in sections
        )
        snapshot["failed"] = sum(
            section["status"] == "failed" for section in sections
        )
        return snapshot


async def _run_draft_all_job(job_id: str, deal_id: str) -> None:
    with _draft_all_jobs_lock:
        _draft_all_jobs[job_id]["status"] = "running"

    def report(
        section_id: str,
        title: str,
        status: str,
        stage: str,
    ) -> None:
        with _draft_all_jobs_lock:
            job = _draft_all_jobs.get(job_id)
            if not job:
                return
            section = next(
                (
                    item
                    for item in job["sections"]
                    if item["section_id"] == section_id
                ),
                None,
            )
            if section:
                section.update(
                    title=title,
                    status=status,
                    stage=stage,
                )

    db = SessionLocal()
    try:
        await NarrativeService.draft_all(db, deal_id, report)
        with _draft_all_jobs_lock:
            _draft_all_jobs[job_id]["status"] = "completed"
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database failure in Draft All job %s", job_id)
        with _draft_all_jobs_lock:
            _draft_all_jobs[job_id].update(
                status="failed",
                error="A database operation failed.",
            )
    except Exception:
        logger.exception("Unexpected failure in Draft All job %s", job_id)
        with _draft_all_jobs_lock:
            _draft_all_jobs[job_id].update(
                status="failed",
                error="Draft All failed unexpectedly.",
            )
    finally:
        db.close()


@router.get("", response_model=list[SectionResponse])
def list_sections(deal_id: str, db: Session = Depends(get_db)):
    """List all sections for a deal."""
    deal = DealService.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal.sections


@router.patch("/{section_id}", response_model=SectionResponse)
async def update_section(
    deal_id: str,
    section_id: str,
    data: SectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update section expected output, custom instructions, output template, or state."""
    update_data = data.model_dump(exclude_unset=True)
    existing_section = _get_deal_section(db, deal_id, section_id)
    if not existing_section:
        raise HTTPException(status_code=404, detail="Section not found")
    previous_content = (
        existing_section.generated_content if existing_section else None
    )
    if existing_section and "generated_content" in update_data:
        NarrativeLockService.require_owner(db, deal_id, section_id, current_user)
        NarrativeVersionService.ensure_current(db, existing_section)
    if "source_urls" in update_data:
        update_data["url_scrape_details"] = None
    section = DealService.update_section(db, section_id, update_data)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if (
        "generated_content" in update_data
        and section.generated_content
        and section.generated_content != previous_content
    ):
        NarrativeVersionService.create(
            db,
            section,
            section.generated_content,
            "edited",
            "Analyst",
        )
        db.commit()
        db.refresh(section)

    # Auto-run moderation when user inputs change
    if "custom_instructions" in update_data or "output_template" in update_data:
        import json as _json
        has_custom = section.custom_instructions and section.custom_instructions.strip()
        has_template = section.output_template and section.output_template.strip()
        if has_custom or has_template:
            moderation = await ModerationService.moderate_section_inputs(
                custom_instructions=section.custom_instructions,
                output_template=section.output_template,
            )
            section.moderation_status = "safe" if moderation.is_safe else "flagged"
            section.moderation_details = _json.dumps(moderation.to_dict())
        else:
            # Both inputs are empty/cleared — remove moderation flags
            section.moderation_status = None
            section.moderation_details = None
        db.commit()
        db.refresh(section)

    DealService.update_deal_status_from_sections(db, deal_id)
    return section


@router.post("/{section_id}/edit-lock", response_model=NarrativeEditLockResponse)
def acquire_narrative_edit_lock(
    deal_id: str,
    section_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Acquire or renew the current user's short narrative editing lease."""
    section = NarrativeLockService.acquire(db, deal_id, section_id, current_user)
    return NarrativeEditLockResponse(
        section_id=section.id,
        locked_by=section.edit_lock_user_name or current_user.user_id,
        expires_at=section.edit_lock_expires_at,
    )


@router.delete("/{section_id}/edit-lock", status_code=204)
def release_narrative_edit_lock(
    deal_id: str,
    section_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    NarrativeLockService.release(db, deal_id, section_id, current_user)


@router.get(
    "/{section_id}/versions",
    response_model=list[NarrativeVersionResponse],
)
def list_narrative_versions(
    deal_id: str,
    section_id: str,
    db: Session = Depends(get_db),
):
    """List generated and edited versions for one narrative."""
    section = _get_deal_section(db, deal_id, section_id)
    if not section or section.deal_id != deal_id:
        raise HTTPException(status_code=404, detail="Section not found")
    return NarrativeVersionService.list_for_section(db, deal_id, section_id)


@router.post(
    "/{section_id}/versions/{version_id}/mark-final",
    response_model=NarrativeVersionResponse,
)
def mark_narrative_version_final(
    deal_id: str,
    section_id: str,
    version_id: str,
    db: Session = Depends(get_db),
):
    """Make one saved version the only final narrative for this section."""
    version = NarrativeVersionService.mark_final(
        db,
        deal_id,
        section_id,
        version_id,
    )
    if not version:
        raise HTTPException(status_code=404, detail="Narrative version not found")
    return version


@router.delete("/{section_id}/versions/{version_id}")
def delete_narrative_version(
    deal_id: str,
    section_id: str,
    version_id: str,
    db: Session = Depends(get_db),
):
    """Delete one narrative version and recalculate the effective final draft."""
    result = NarrativeVersionService.delete(
        db,
        deal_id,
        section_id,
        version_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Narrative version not found")
    return result


@router.post("/{section_id}/generate", response_model=NarrativeResponse)
async def generate_narrative(
    deal_id: str,
    section_id: str,
    body: NarrativeRequest | None = None,
    db: Session = Depends(get_db),
):
    """Generate AI narrative for a single section using its dedicated Mistral agent."""
    deal = DealService.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    if deal.library_sync_status == "syncing" and not (
        deal.company_mistral_library_id or deal.mistral_library_id
    ):
        raise HTTPException(
            status_code=409, 
            detail="Library sync in progress. Please wait until documents are fully uploaded."
        )

    custom_instructions = body.custom_instructions if body else None
    try:
        section, orchestration_strategy = await NarrativeService.generate_section(
            db, deal_id, section_id, custom_instructions
        )
    except ValueError:
        logger.warning("Section generation rejected for deal %s section %s", deal_id, section_id)
        raise HTTPException(
            status_code=400,
            detail="Section generation could not be completed with the supplied inputs.",
        )
    if not section:
        raise HTTPException(status_code=404, detail="Deal or section not found")

    # Parse accuracy_details from JSON string if present
    accuracy_details = None
    if section.accuracy_details:
        import json
        try:
            accuracy_details = json.loads(section.accuracy_details)
        except (json.JSONDecodeError, TypeError):
            pass

    return NarrativeResponse(
        section_id=section.id,
        section_key=section.section_key,
        title=section.title,
        generated_content=section.generated_content or "",
        state=section.state,
        accuracy_score=section.accuracy_score,
        accuracy_details=accuracy_details,
        orchestration_strategy=orchestration_strategy,
    )


@router.post(
    "/generate-all/start",
    response_model=DraftAllJobResponse,
    status_code=202,
)
def start_draft_all_job(
    deal_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Start Draft All and return an ID for live per-section progress."""
    deal = DealService.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    if deal.library_sync_status == "syncing" and not (
        deal.company_mistral_library_id or deal.mistral_library_id
    ):
        raise HTTPException(
            status_code=409,
            detail="Library sync is still in progress.",
        )
    with _draft_all_jobs_lock:
        existing = next(
            (
                job
                for job in _draft_all_jobs.values()
                if job["deal_id"] == deal_id
                and job["status"] in {"queued", "running"}
            ),
            None,
        )
        if existing:
            job_id = existing["job_id"]
        else:
            job_id = "draft_" + uuid.uuid4().hex[:12]
            _draft_all_jobs[job_id] = {
                "job_id": job_id,
                "deal_id": deal_id,
                "status": "queued",
                "percent": 0,
                "completed": 0,
                "failed": 0,
                "total": len(deal.sections),
                "sections": [
                    {
                        "section_id": section.id,
                        "title": section.title,
                        "status": "queued",
                        "stage": "Queued",
                    }
                    for section in deal.sections
                ],
                "error": None,
            }
            background_tasks.add_task(_run_draft_all_job, job_id, deal_id)
    snapshot = _draft_job_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=500, detail="Could not start Draft All.")
    return snapshot


@router.get(
    "/generate-all/jobs/{job_id}",
    response_model=DraftAllJobResponse,
)
def get_draft_all_job(deal_id: str, job_id: str):
    """Return current per-section Draft All progress."""
    snapshot = _draft_job_snapshot(job_id)
    if not snapshot or snapshot["deal_id"] != deal_id:
        raise HTTPException(status_code=404, detail="Draft All job not found")
    return snapshot


@router.post("/generate-all", response_model=DraftAllResponse)
async def draft_all_sections(deal_id: str, db: Session = Depends(get_db)):
    """
    Generate narratives for ALL sections in parallel.
    Each section has its own dedicated Mistral agent.
    All agents run concurrently via asyncio.gather().
    """
    deal = DealService.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    if deal.library_sync_status == "syncing" and not (
        deal.company_mistral_library_id or deal.mistral_library_id
    ):
        raise HTTPException(
            status_code=409, 
            detail="Library sync in progress. Please wait until documents are fully uploaded."
        )

    results = await NarrativeService.draft_all(db, deal_id)
    if not results:
        raise HTTPException(status_code=404, detail="Deal not found")

    succeeded = sum(1 for r in results if r.get("success"))
    return DraftAllResponse(
        results=[
            NarrativeResponse(
                section_id=r["section_id"],
                section_key=r["section_key"],
                title=r["title"],
                generated_content=r["generated_content"],
                state=r["state"],
                accuracy_score=r.get("accuracy", {}).get("score") if r.get("accuracy") else None,
                accuracy_details=r.get("accuracy"),
                orchestration_strategy=r.get("orchestration_strategy"),
                timing=r.get("timing"),
            )
            for r in results
        ],
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


# ── Content Moderation ──────────────────────────────────────────

@router.post("/{section_id}/moderate")
async def moderate_section(
    deal_id: str,
    section_id: str,
    db: Session = Depends(get_db),
):
    """
    Run content moderation on a section's user-provided inputs.
    Returns moderation status and flagged categories.
    """
    import json as _json
    section = _get_deal_section(db, deal_id, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    if not section.custom_instructions and not section.output_template:
        section.moderation_status = None
        section.moderation_details = None
        db.commit()
        db.refresh(section)
        return {
            "moderation_status": None,
            "is_safe": True,
            "flagged_categories": [],
            "message": "No user inputs to moderate.",
        }

    moderation = await ModerationService.moderate_section_inputs(
        custom_instructions=section.custom_instructions,
        output_template=section.output_template,
    )

    section.moderation_status = "safe" if moderation.is_safe else "flagged"
    section.moderation_details = _json.dumps(moderation.to_dict())
    db.commit()
    db.refresh(section)

    return {
        "moderation_status": section.moderation_status,
        "is_safe": moderation.is_safe,
        "flagged_categories": moderation.flagged_categories,
        "details": moderation.details,
        "message": (
            "Content passed moderation."
            if moderation.is_safe
            else f"Content flagged: {', '.join(moderation.flagged_categories)}. "
                 f"Please edit your inputs before generating."
        ),
    }


# ── Template Management ────────────────────────────────────────

SUPPORTED_TEMPLATE_EXTENSIONS = TEMPLATE_EXTENSIONS


@router.post("/{section_id}/template", response_model=SectionResponse)
async def upload_template(
    deal_id: str,
    section_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload an output template file for a section.
    Supports .md, .txt, and .docx files.
    The template content is extracted and stored as markdown text
    that the AI agent will follow when generating the narrative.
    """
    section = _get_deal_section(db, deal_id, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    file_bytes = await file.read()
    try:
        filename = validate_uploaded_file(
            file.filename, file_bytes, allowed_extensions=TEMPLATE_EXTENSIONS
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ext = Path(filename).suffix.lower()

    template_text = extract_text_preview(file_bytes, filename)
    try:
        SectionUpdate(output_template=template_text)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Template must contain plain text or Markdown without HTML markup, within 100000 characters.") from exc

    # Save template file to disk
    template_dir = settings.upload_path / deal_id / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    file_path = template_dir / safe_name

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Extract text content from the template file

    # Update section with template
    section.output_template = template_text
    section.template_file_path = str(file_path)
    db.commit()
    db.refresh(section)

    return section


@router.delete("/{section_id}/template", response_model=SectionResponse)
def delete_template(
    deal_id: str,
    section_id: str,
    db: Session = Depends(get_db),
):
    """Remove the output template from a section."""
    section = _get_deal_section(db, deal_id, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # Delete template file from disk
    if section.template_file_path and os.path.exists(section.template_file_path):
        try:
            os.remove(section.template_file_path)
        except Exception:
            pass

    section.output_template = None
    section.template_file_path = None

    # Re-evaluate moderation: if no user inputs remain, clear moderation flags
    has_custom = section.custom_instructions and section.custom_instructions.strip()
    if not has_custom:
        section.moderation_status = None
        section.moderation_details = None

    db.commit()
    db.refresh(section)

    return section
