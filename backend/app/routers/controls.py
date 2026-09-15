from fastapi import APIRouter, Depends
from ..database import shared_policy_connection
from ..security import current_user

router = APIRouter()

@router.get("/api/controls")
def controls(_: dict = Depends(current_user)):
    with shared_policy_connection() as connection:
        return connection.execute("""
            SELECT control.control_id, control.policy_id, document.library_policy_id,
                   control.policy_code, control.policy_name, control.control_sequence,
                   control.control_name, control.control_owner, control.clause_number,
                   control.control_type, control.automation, control.frequency,
                   control.effectiveness, control.status, control.last_tested,
                   control.failures_90d, control.control_description,
                   control.assessment, control.generated_at
            FROM policy_controls control
            JOIN policy_documents document ON document.policy_id = control.policy_id
            ORDER BY SPLIT_PART(document.library_policy_id, '.', 1)::INTEGER,
                     SPLIT_PART(document.library_policy_id, '.', 2)::INTEGER,
                     control.control_sequence
        """).fetchall()
