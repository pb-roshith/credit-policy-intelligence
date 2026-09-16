from datetime import date, timedelta
import json
import re
import secrets
from fastapi import APIRouter, Depends, HTTPException
from ..config import BORROWER_PREFIXES, BORROWER_SUFFIXES, GEOGRAPHIES, GEOGRAPHY_RISK, INDUSTRY_FACILITIES, RATINGS, REQUEST_STATUSES
from ..database import db_connection, resolve_borrower
from ..schemas import CreateCreditRequest, GenerateBorrowerExposureRequest, GenerateCreditRequestsRequest, GenerateExceptionsRequest, GeneratePolicyControlsRequest, PolicyClauseEvaluation
from ..security import current_user
from ..services.compliance_scoring import calculate_compliance_score, persist_compliance_result

router = APIRouter(prefix="/api/data-manufacturing", tags=["data manufacturing"])

EXCEPTION_TYPES = [
    ("Leverage", "CP-4.2"),
    ("Collateral", "COL-2.1"),
    ("Concentration", "RAF-3.5"),
    ("Covenant", "CP-6.4"),
    ("Tenor", "CP-4.3"),
]

@router.post("/credit-requests", status_code=201)
def generate_credit_requests(payload: GenerateCreditRequestsRequest, user: dict = Depends(current_user)):
    generated = []
    with db_connection() as connection:
        # Serialize number allocation so simultaneous generators cannot create the same request number.
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('credit_requests'))")
        next_number = connection.execute("""
            SELECT COALESCE(MAX(SUBSTRING(credit_request_number FROM 4)::BIGINT), 10240) + 1 AS value
            FROM credit_requests
            WHERE credit_request_number ~ '^CR-[0-9]+$'
        """).fetchone()["value"]
        for offset in range(payload.count):
            industry, facility = secrets.choice(INDUSTRY_FACILITIES)
            geography = secrets.choice(GEOGRAPHIES)
            requested_amount = (5 + secrets.randbelow(116)) * 1_000_000
            exposure = requested_amount + (10 + secrets.randbelow(241)) * 1_000_000
            status = secrets.choice(REQUEST_STATUSES)
            post_approval_exposure = exposure + requested_amount
            synthetic_payload = CreateCreditRequest(
                borrower_name=f"{secrets.choice(BORROWER_PREFIXES)} {secrets.choice(BORROWER_SUFFIXES)} {next_number + offset}",
                industry=industry,
                geography=geography,
                facility=facility,
                rating=secrets.choice(RATINGS),
                requested_amount=requested_amount,
                status=status,
                collateral_coverage=100,
                geography_risk=GEOGRAPHY_RISK[geography],
                concentration_limit_utilization=50 + secrets.randbelow(71),
                adjusted_collateral=post_approval_exposure * (70 + secrets.randbelow(71)) // 100,
                approval_authority=secrets.choice(["Credit Officer", "Senior Credit Officer", "Credit Committee", "Executive Committee"]),
                total_required_documents=5,
                uploaded_required_documents=secrets.randbelow(6),
                policy_clauses=[
                    PolicyClauseEvaluation(clause_code=code, clause_name=name, result=secrets.choice(["PASS", "PASS", "WARNING", "FAIL"]))
                    for code, name in [
                        ("CP-4.2", "Leverage Limit"), ("COL-2.1", "Collateral Eligibility"),
                        ("CP-4.3", "Tenor Limit"), ("CP-4.4", "Covenant Package"),
                    ]
                ],
            )
            compliance, required_authority = calculate_compliance_score(
                connection, synthetic_payload, post_approval_exposure,
            )
            row = {
                "credit_request_number": f"CR-{next_number + offset:05d}",
                "borrower_id": resolve_borrower(connection, synthetic_payload.borrower_name),
                "borrower_name": synthetic_payload.borrower_name,
                "industry": industry,
                "geography": synthetic_payload.geography,
                "exposure": exposure,
                "facility": facility,
                "rating": synthetic_payload.rating,
                "requested_amount": requested_amount,
                "status": status,
                "compliance_score": round(compliance["overallScore"]),
                "collateral_coverage": round(synthetic_payload.adjusted_collateral / post_approval_exposure * 100, 2),
                "recommended_pricing_bps": 325,
                "recommended_tenor_years": 3 if facility in {"Bridge", "Construction"} else 5 if facility == "Revolver" else 7,
            }
            connection.execute("""
                INSERT INTO credit_requests (
                    credit_request_number, borrower_id, borrower_name, industry, geography, exposure, facility,
                    rating, requested_amount, status, compliance_score
                    , collateral_coverage, recommended_pricing_bps, recommended_tenor_years
                ) VALUES (%(credit_request_number)s, %(borrower_id)s, %(borrower_name)s, %(industry)s, %(geography)s,
                          %(exposure)s, %(facility)s, %(rating)s, %(requested_amount)s,
                          %(status)s, %(compliance_score)s, %(collateral_coverage)s,
                          %(recommended_pricing_bps)s, %(recommended_tenor_years)s)
            """, row)
            persist_compliance_result(
                connection, row["credit_request_number"], synthetic_payload,
                post_approval_exposure, compliance, required_authority,
            )
            generated.append(row)
    return {"message": f"Generated {payload.count} credit request{'s' if payload.count != 1 else ''}", "count": payload.count, "generated_by": user["user_id"], "credit_requests": generated}


@router.post("/exceptions", status_code=201)
def generate_exceptions(payload: GenerateExceptionsRequest, user: dict = Depends(current_user)):
    """Create one synthetic exception for every selected account-owned credit request."""
    selected = payload.credit_request_numbers
    generated = []
    with db_connection() as connection:
        requests = connection.execute("""
            SELECT credit_request_number, borrower_name, industry, facility, rating, exposure
            FROM credit_requests
            WHERE credit_request_number = ANY(%s)
        """, (selected,)).fetchall()
        by_number = {row["credit_request_number"]: row for row in requests}
        missing = [number for number in selected if number not in by_number]
        if missing:
            raise HTTPException(status_code=404, detail=f"Credit request not found: {', '.join(missing)}")

        connection.execute("SELECT pg_advisory_xact_lock(hashtext('credit_request_exceptions'))")
        next_number = connection.execute("""
            SELECT GREATEST(9000, COALESCE(MAX(NULLIF(regexp_replace(exception_id, '\\D', '', 'g'), '')::BIGINT), 9000)) + 1 AS value
            FROM credit_request_exceptions
        """).fetchone()["value"]

        for offset, request_number in enumerate(selected):
            request = by_number[request_number]
            exception_type, clause = secrets.choice(EXCEPTION_TYPES)
            exposure = int(request["exposure"])
            severity = "Low" if exposure < 25_000_000 else "Medium" if exposure < 75_000_000 else "High"
            due_date = date.today() + timedelta(days=30 + secrets.randbelow(31))
            exception_id = f"EX-{next_number + offset}"
            description = (
                f"Manufactured {exception_type.lower()} exception for {request_number} "
                f"to support exception workflow testing."
            )
            rationale = {
                "why_detected": f"The selected {request['industry']} request was assigned a synthetic {exception_type.lower()} policy exception.",
                "business_justification": "Generated for controlled testing of the exception review and remediation workflow.",
                "risk_implication": f"The exception represents illustrative {exception_type.lower()} risk against {clause}.",
                "recommended_remediation": "Review the selected request, document mitigating controls, and complete the remediation workflow.",
                "escalation_required": "Escalate if the generated exception is not addressed before its due date.",
            }
            workflow = [
                {"name": "Detected", "status": "Done"},
                {"name": "Reviewed", "status": "Current"},
                {"name": "Approved", "status": "Pending"},
                {"name": "Remediated", "status": "Pending"},
                {"name": "Closed", "status": "Pending"},
            ]
            history = [{"date": str(date.today()), "event": "Generated from Data Manufacturing", "actor": user["user_id"]}]
            row = connection.execute("""
                INSERT INTO credit_request_exceptions
                    (exception_id, credit_request_number, exception_type, clause_code, severity,
                     exposure, owner, due_date, status, description, rationale, workflow, history)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Active',%s,%s::jsonb,%s::jsonb,%s::jsonb)
                RETURNING exception_id AS id, credit_request_number, exception_type AS type,
                          clause_code AS clause, severity, exposure, owner, due_date AS due, status
            """, (
                exception_id, request_number, exception_type, clause, severity, exposure,
                user["user_id"], due_date, description, json.dumps(rationale),
                json.dumps(workflow), json.dumps(history),
            )).fetchone()
            generated.append(dict(row))

    count = len(generated)
    return {
        "message": f"Generated {count} exception{'s' if count != 1 else ''}",
        "count": count,
        "generated_by": user["user_id"],
        "exceptions": generated,
    }
