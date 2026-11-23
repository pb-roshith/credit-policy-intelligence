"""Background API for manufacturing local MCP credit data."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.config import settings
from app.models.user import User


router = APIRouter(
    prefix="/api/manufacture",
    tags=["manufacture"],
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MCP_DIR = REPOSITORY_ROOT / "mcp"
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="manufacture")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class ManufactureRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=256)
    industry: str = Field(min_length=2, max_length=256)
    geography: str = Field(min_length=2, max_length=256)


class ManufactureJob(BaseModel):
    job_id: str
    status: str
    percent: int
    stage: str
    result: dict[str, Any] | None = None
    error: str | None = None
    phase: str = "queued"
    generated_pdfs: list[str] = Field(default_factory=list)
    uploaded_pdfs: list[str] = Field(default_factory=list)
    completed_tables: list[str] = Field(default_factory=list)
    pdf_total: int = 17
    table_total: int = 16


def _progress_percent(phase: str, completed: int, total: int) -> int:
    ranges = {
        "initialization": (1, 4),
        "context": (4, 8),
        "pdf_generation": (8, 48),
        "table_generation": (48, 62),
        "pdf_upload": (62, 84),
        "table_seed": (84, 99),
    }
    start, end = ranges.get(phase, (1, 99))
    return min(99, round(start + (end - start) * completed / max(total, 1)))


def _apply_progress(job_id: str, event: dict[str, Any]) -> None:
    phase = str(event.get("phase") or "running")
    completed = int(event.get("completed") or 0)
    total = int(event.get("total") or 1)
    item = event.get("item")
    with _jobs_lock:
        job = _jobs[job_id]
        if item and phase == "pdf_generation" and item not in job["generated_pdfs"]:
            job["generated_pdfs"].append(item)
        elif item and phase == "pdf_upload" and item not in job["uploaded_pdfs"]:
            job["uploaded_pdfs"].append(item)
        elif item and phase == "table_seed" and item not in job["completed_tables"]:
            job["completed_tables"].append(item)
        job.update(
            phase=phase,
            stage=str(event.get("stage") or "Manufacturing data"),
            percent=_progress_percent(phase, completed, total),
        )


def _set_job(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        _jobs[job_id].update(updates)


def _run_manufacturing(job_id: str, owner_key: str, request: ManufactureRequest) -> None:
    _set_job(
        job_id,
        status="running",
        percent=10,
        stage="Generating PDFs, uploading to Mistral, and seeding PostgreSQL",
    )
    command = [
        sys.executable,
        "manufacture.py",
        "--owner-user-id",
        owner_key,
        "--company-name",
        request.company_name,
        "--industry",
        request.industry,
        "--geography",
        request.geography,
        "--json",
        "--progress-json",
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=MCP_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        output_lines: list[str] = []
        timed_out = threading.Event()

        def expire_process() -> None:
            timed_out.set()
            process.kill()

        timeout_timer = threading.Timer(
            settings.MANUFACTURE_TIMEOUT_SECONDS, expire_process
        )
        timeout_timer.start()
        assert process.stdout is not None
        try:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                output_lines.append(line)
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    message = None
                if isinstance(message, dict) and message.get("type") == "progress":
                    _apply_progress(job_id, message)
        finally:
            timeout_timer.cancel()
        return_code = process.wait()
        if timed_out.is_set():
            raise TimeoutError(
                f"Manufacturing exceeded {settings.MANUFACTURE_TIMEOUT_SECONDS} seconds."
            )
        if return_code != 0:
            error = "\n".join(output_lines[-20:])
            raise RuntimeError(error or "Manufacturing process failed.")
        if not output_lines:
            raise RuntimeError("Manufacturing process returned no result.")
        result = None
        for line in reversed(output_lines):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and candidate.get("type") != "progress":
                result = candidate
                break
        if result is None:
            raise RuntimeError("Manufacturing process returned no final result.")
        from app.services.mcp_service import MCPClientService
        MCPClientService.invalidate_cache(request.company_name, owner_key)
        _set_job(
            job_id,
            status="completed",
            percent=100,
            stage="Manufacturing completed",
            phase="completed",
            result=result,
        )
    except Exception as exc:
        _set_job(
            job_id,
            status="failed",
            percent=100,
            stage="Manufacturing failed",
            phase="failed",
            error=str(exc),
        )


@router.post("", response_model=ManufactureJob, status_code=202)
def start_manufacturing(
    request: ManufactureRequest,
    current_user: User = Depends(get_current_user),
) -> ManufactureJob:
    """Start one background manufacturing job."""
    if not (MCP_DIR / "manufacture.py").exists():
        raise HTTPException(status_code=500, detail="Local MCP service is missing.")
    job_id = "mfg_" + uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "status": "queued",
        "percent": 0,
        "stage": "Queued for manufacturing",
        "result": None,
        "error": None,
        "owner_user_id": current_user.id,
        "phase": "queued",
        "generated_pdfs": [],
        "uploaded_pdfs": [],
        "completed_tables": [],
        "pdf_total": 17,
        "table_total": 16,
    }
    with _jobs_lock:
        _jobs[job_id] = job
    _executor.submit(_run_manufacturing, job_id, current_user.user_id, request)
    return ManufactureJob(**job)


@router.get("/{job_id}", response_model=ManufactureJob)
def get_manufacturing_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> ManufactureJob:
    """Return current progress and the final manufacturing result."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        snapshot = (
            dict(job)
            if job and job.get("owner_user_id") == current_user.id
            else None
        )
    if not snapshot:
        raise HTTPException(status_code=404, detail="Manufacturing job not found.")
    return ManufactureJob(**snapshot)
