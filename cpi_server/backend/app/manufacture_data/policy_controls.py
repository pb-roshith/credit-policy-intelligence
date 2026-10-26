from datetime import date, timedelta
import re
import secrets
from fastapi import APIRouter, Depends, HTTPException
from ..config import BORROWER_PREFIXES, BORROWER_SUFFIXES, INDUSTRY_FACILITIES, RATINGS, REQUEST_STATUSES
from ..database import shared_policy_connection, resolve_borrower
from ..schemas import CreateCreditRequest, GenerateBorrowerExposureRequest, GenerateCreditRequestsRequest, GeneratePolicyControlsRequest
from ..security import current_user
from ..services.compliance_scoring import calculate_compliance_score, persist_compliance_result

router = APIRouter(prefix="/api/data-manufacturing", tags=["data manufacturing"])

@router.post("/policy-controls", status_code=201)
def generate_policy_controls(payload: GeneratePolicyControlsRequest, user: dict = Depends(current_user)):
    templates = [
        ("Eligibility and Threshold Validation", "Credit Risk", "Preventive", "Automated", "Per Deal"),
        ("Approval Authority Verification", "Credit Governance", "Preventive", "Semi-automated", "Per Deal"),
        ("Ongoing Limit Monitoring", "Portfolio Risk", "Detective", "Automated", "Daily"),
        ("Exception Escalation Review", "Policy Governance", "Corrective", "Manual", "Monthly"),
        ("Evidence and Compliance Reconciliation", "Compliance", "Detective", "Semi-automated", "Quarterly"),
    ]
    with shared_policy_connection() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('policy_controls'))")
        policies = connection.execute("""
            SELECT policy_id, policy_code, library_policy_id, title, clause_number
            FROM policy_documents
            ORDER BY display_order, policy_id
        """).fetchall()
        if not policies:
            raise HTTPException(
                status_code=422,
                detail="Generate or import policy documents before manufacturing controls",
            )

        connection.execute(
            "DELETE FROM policy_controls WHERE control_sequence > %s",
            (payload.controls_per_policy,),
        )
        for policy in policies:
            for sequence, (suffix, owner, control_type, automation, frequency) in enumerate(
                templates[:payload.controls_per_policy], start=1
            ):
                effectiveness = 72 + ((policy["policy_id"] * 7 + sequence * 5) % 27)
                status = (
                    "Effective" if effectiveness >= 85
                    else "Needs Improvement" if effectiveness >= 75
                    else "Ineffective"
                )
                failures = max(0, (88 - effectiveness) // 4)
                control_id = f"CTL-{policy['policy_id']:05d}-{sequence:02d}"
                policy_name = re.sub(
                    r"^(?:(?:[A-Z]\.)?\d+(?:\.\d+)?|POL-\d+)\s+",
                    "",
                    policy["title"],
                )
                control_name = f"{policy_name} - {suffix}"[:240]
                control_description = (
                    f"{control_name} verifies the requirements of {policy_name} "
                    f"(Policy ID {policy['library_policy_id']}) for clause "
                    f"{policy['clause_number']}. It records supporting evidence, identifies "
                    f"exceptions, and routes unresolved findings to {owner}."
                )
                assessment = (
                    f"{control_id} is mapped to Policy ID {policy['library_policy_id']}, "
                    f"{policy['policy_code']} ({policy_name}). "
                    f"The manufactured effectiveness score is {effectiveness}% with {failures} "
                    f"failure{'s' if failures != 1 else ''} in the assumed 90-day testing period. "
                    f"Current control status: {status}."
                )
                connection.execute("""
                    INSERT INTO policy_controls (
                        control_id, policy_id, policy_code, policy_name, control_sequence,
                        control_name, control_owner, clause_number, control_type, automation,
                        frequency, effectiveness, status, last_tested, failures_90d,
                        control_description, assessment,
                        generated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              CURRENT_TIMESTAMP)
                    ON CONFLICT (policy_id, control_sequence) DO UPDATE SET
                        control_id = EXCLUDED.control_id,
                        policy_code = EXCLUDED.policy_code,
                        policy_name = EXCLUDED.policy_name,
                        control_name = EXCLUDED.control_name,
                        control_owner = EXCLUDED.control_owner,
                        clause_number = EXCLUDED.clause_number,
                        control_type = EXCLUDED.control_type,
                        automation = EXCLUDED.automation,
                        frequency = EXCLUDED.frequency,
                        effectiveness = EXCLUDED.effectiveness,
                        status = EXCLUDED.status,
                        last_tested = EXCLUDED.last_tested,
                        failures_90d = EXCLUDED.failures_90d,
                        control_description = EXCLUDED.control_description,
                        assessment = EXCLUDED.assessment,
                        generated_at = CURRENT_TIMESTAMP
                """, (
                    control_id, policy["policy_id"], policy["policy_code"], policy_name,
                    sequence, control_name, owner, policy["clause_number"], control_type,
                    automation, frequency, effectiveness, status,
                    date.today() - timedelta(days=(policy["policy_id"] + sequence * 9) % 60),
                    failures, control_description, assessment,
                ))
        control_count = connection.execute(
            "SELECT COUNT(*) AS count FROM policy_controls"
        ).fetchone()["count"]

    return {
        "message": (
            f"Generated {payload.controls_per_policy} controls for each of "
            f"{len(policies)} policy documents"
        ),
        "policy_count": len(policies),
        "controls_per_policy": payload.controls_per_policy,
        "control_count": control_count,
        "generated_by": user["user_id"],
    }
