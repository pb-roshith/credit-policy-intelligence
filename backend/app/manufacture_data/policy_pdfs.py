import secrets
import threading
from fastapi import APIRouter, Depends, HTTPException
from ..config import (MISTRAL_API_KEY, MISTRAL_POLICY_MODEL, POLICY_JOB_LOCK,
                      POLICY_OUTPUT_DIR, POLICY_SOURCE_DIR)
from ..database import shared_policy_connection
from ..security import current_user
from .policy_generation_service import (
    GENERATED_DOCUMENT_COUNT, IMPORTED_DOCUMENT_COUNT,
    POLICY_LIBRARY_DOCUMENT_COUNT, run_policy_generation,
)

router = APIRouter(prefix="/api/data-manufacturing", tags=["data manufacturing"])

def public_policy_job(row: dict | None) -> dict:
    if not row:
        return {
            "status": "idle", "total_documents": POLICY_LIBRARY_DOCUMENT_COUNT, "completed_documents": 0,
            "message": "No policy generation job has been started",
        }
    return {
        "job_id": row["job_id"],
        "status": row["status"],
        "total_documents": row["total_documents"],
        "completed_documents": row["completed_documents"],
        "current_policy": row["current_policy"],
        "message": row["message"],
        "error": row["error"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


@router.get("/policy-pdfs/status")
def latest_policy_generation_status(_: dict = Depends(current_user)):
    with shared_policy_connection() as connection:
        row = connection.execute(
            "SELECT * FROM policy_generation_jobs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        document_count = connection.execute(
            """SELECT COUNT(*) AS count FROM policy_documents
               WHERE source_type IN ('manufactured', 'imported')"""
        ).fetchone()["count"]
    result = public_policy_job(row)
    result["stored_documents"] = document_count
    return result


@router.get("/policy-pdfs/{job_id}")
def policy_generation_status(job_id: str, _: dict = Depends(current_user)):
    with shared_policy_connection() as connection:
        row = connection.execute(
            "SELECT * FROM policy_generation_jobs WHERE job_id = %s", (job_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Policy generation job not found")
    return public_policy_job(row)


@router.post("/policy-pdfs", status_code=202)
def generate_policy_pdfs(user: dict = Depends(current_user)):
    if not MISTRAL_API_KEY:
        raise HTTPException(status_code=503, detail="MISTRAL_API_KEY is not configured")
    with POLICY_JOB_LOCK:
        with shared_policy_connection() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('policy_generation'))")
            counts = connection.execute("""
                SELECT COUNT(*) FILTER (WHERE source_type = 'manufactured') AS generated,
                       COUNT(*) FILTER (WHERE source_type = 'imported') AS imported
                FROM policy_documents
            """).fetchone()
            stored_count = min(counts["generated"], GENERATED_DOCUMENT_COUNT) + min(counts["imported"], IMPORTED_DOCUMENT_COUNT)
            if counts["generated"] >= GENERATED_DOCUMENT_COUNT and counts["imported"] >= IMPORTED_DOCUMENT_COUNT:
                return {
                    "status": "completed", "total_documents": POLICY_LIBRARY_DOCUMENT_COUNT,
                    "completed_documents": POLICY_LIBRARY_DOCUMENT_COUNT,
                    "message": "All 35 policy files are already stored in the shared Mistral library",
                }
            active = connection.execute("""
                SELECT * FROM policy_generation_jobs
                WHERE status IN ('queued', 'running') ORDER BY created_at DESC LIMIT 1
            """).fetchone()
            if active:
                return public_policy_job(active)
            job_id = secrets.token_hex(16)
            connection.execute("""
                INSERT INTO policy_generation_jobs
                    (job_id, status, total_documents, completed_documents, message, initiated_by)
                VALUES (%s, 'queued', %s, %s, 'Policy generation queued', %s)
            """, (job_id, POLICY_LIBRARY_DOCUMENT_COUNT, stored_count, user["user_id"]))
        worker = threading.Thread(
            target=run_policy_generation,
            args=(job_id, shared_policy_connection, MISTRAL_API_KEY,
                  POLICY_OUTPUT_DIR, POLICY_SOURCE_DIR, MISTRAL_POLICY_MODEL),
            name=f"policy-generation-{job_id[:8]}", daemon=True,
        )
        worker.start()
    return {
        "job_id": job_id, "status": "queued", "total_documents": POLICY_LIBRARY_DOCUMENT_COUNT,
        "completed_documents": stored_count, "message": "Policy generation started",
    }

