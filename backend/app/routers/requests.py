from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation
from ..config import GEOGRAPHY_RISK
from ..database import db_connection, resolve_borrower
from ..schemas import CreateCreditRequest
from ..security import current_user
from ..services.compliance_scoring import calculate_compliance_score, persist_compliance_result, public_credit_request

router = APIRouter()

@router.get("/api/health")
def health():
    return {"status": "ok", "service": "credit-policy-intelligence", "date": date.today()}

@router.get("/api/summary")
def summary(_: dict = Depends(current_user)):
    with db_connection() as connection:
        active_requests = connection.execute(
            "SELECT COUNT(*) AS count FROM credit_requests"
        ).fetchone()["count"]
    return {"exposure": 4_820_000_000, "ecl_provision": 312_600_000, "policy_compliance": 92, "open_exceptions": 148, "active_requests": active_requests}

@router.get("/api/requests")
def credit_requests(status: str | None = None, _: dict = Depends(current_user)):
    query = """
        WITH borrower_exposure AS (
            SELECT borrower_id,
                   SUM(outstanding_exposure)::BIGINT AS exposure
            FROM latest_borrower_exposure
            GROUP BY borrower_id
        )
        SELECT cr.credit_request_number, cr.borrower_id, cr.borrower_name, cr.industry, cr.geography,
               COALESCE(be.exposure, cr.exposure) AS exposure, cr.facility,
               cr.rating, cr.requested_amount, cr.status, cr.compliance_score,
               cr.collateral_coverage, cr.recommended_pricing_bps, cr.recommended_tenor_years
        FROM credit_requests cr
        LEFT JOIN borrower_exposure be ON be.borrower_id = cr.borrower_id
    """
    parameters: tuple = ()
    if status:
        query += " WHERE LOWER(cr.status) = LOWER(%s)"
        parameters = (status,)
    query += " ORDER BY cr.compliance_score ASC, cr.credit_request_number ASC"
    with db_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [public_credit_request(row) for row in rows]


@router.post("/api/requests", status_code=201)
def create_credit_request(payload: CreateCreditRequest, user: dict = Depends(current_user)):
    if user["role"] != "relationship_manager":
        raise HTTPException(status_code=403, detail="Only relationship managers can create credit requests")
    if payload.uploaded_required_documents > payload.total_required_documents:
        raise HTTPException(status_code=422, detail="Uploaded required documents cannot exceed total required documents")
    compliance_fields = {
        "geography_risk", "concentration_limit_utilization", "adjusted_collateral",
        "approval_authority", "total_required_documents", "uploaded_required_documents",
        "policy_clauses",
    }
    values = payload.model_dump(exclude=compliance_fields)
    values["borrower_name"] = values["borrower_name"].strip()
    try:
        with db_connection() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('credit_requests'))")
            next_number = connection.execute("""
                SELECT COALESCE(MAX(SUBSTRING(credit_request_number FROM 4)::BIGINT), 10240) + 1 AS value
                FROM credit_requests
                WHERE credit_request_number ~ '^CR-[0-9]+$'
            """).fetchone()["value"]
            values["borrower_id"] = resolve_borrower(connection, values["borrower_name"], payload.borrower_id)
            derived_exposure = connection.execute("""
                SELECT SUM(outstanding_exposure)::BIGINT AS exposure
                FROM latest_borrower_exposure
                WHERE borrower_id = %s
            """, (values["borrower_id"],)).fetchone()["exposure"]
            values["credit_request_number"] = f"CR-{next_number:05d}"
            values["exposure"] = derived_exposure or 0
            post_approval_exposure = values["exposure"] + values["requested_amount"]
            geography_risk = GEOGRAPHY_RISK[payload.geography]
            concentration_utilization = round(post_approval_exposure / 150_000_000 * 100, 2)
            required_authority = connection.execute("""
                SELECT authority_name FROM approval_authority_rules
                WHERE maximum_post_approval_exposure IS NULL OR %s <= maximum_post_approval_exposure
                ORDER BY rule_order LIMIT 1
            """, (post_approval_exposure,)).fetchone()["authority_name"]
            rating = payload.rating.strip().upper()
            rating_signal = "PASS" if rating.startswith(("AAA", "AA", "A", "BBB")) else "WARNING" if rating.startswith("BB") else "FAIL"
            coverage_signal = "PASS" if payload.collateral_coverage >= 120 else "WARNING" if payload.collateral_coverage >= 80 else "FAIL"
            derived_payload = CreateCreditRequest.model_validate({**payload.model_dump(), **{
                "geography_risk": geography_risk,
                "concentration_limit_utilization": concentration_utilization,
                "adjusted_collateral": round(post_approval_exposure * payload.collateral_coverage / 100),
                "approval_authority": required_authority,
                "policy_clauses": [
                    {"clause_code": "CP-4.2", "clause_name": "Leverage and borrower risk", "result": rating_signal},
                    {"clause_code": "COL-2.1", "clause_name": "Collateral coverage", "result": coverage_signal},
                    {"clause_code": "PRC-1.1", "clause_name": "Risk-based pricing", "result": "PASS"},
                    {"clause_code": "CP-4.3", "clause_name": "Recommended tenor", "result": "PASS"},
                    {"clause_code": "CP-4.4", "clause_name": "Documentation and covenants", "result": "PASS" if payload.uploaded_required_documents == payload.total_required_documents else "WARNING"},
                ],
            }})
            compliance, required_authority = calculate_compliance_score(
                connection, derived_payload, post_approval_exposure
            )
            values["compliance_score"] = round(compliance["overallScore"])
            values["recommended_pricing_bps"] = 225 if rating.startswith(("AAA", "AA", "A")) else 275 if rating.startswith("BBB") else 325 if rating.startswith("BB") else 450
            facility = payload.facility.strip().casefold()
            values["recommended_tenor_years"] = 3 if facility in {"bridge", "construction"} else 5 if facility == "revolver" else 7
            row = connection.execute("""
                INSERT INTO credit_requests (
                    credit_request_number, borrower_id, borrower_name, industry, geography, exposure, facility,
                    rating, requested_amount, status, compliance_score
                    , collateral_coverage, recommended_pricing_bps, recommended_tenor_years
                ) VALUES (%(credit_request_number)s, %(borrower_id)s, %(borrower_name)s, %(industry)s, %(geography)s,
                          %(exposure)s, %(facility)s, %(rating)s, %(requested_amount)s,
                          %(status)s, %(compliance_score)s, %(collateral_coverage)s,
                          %(recommended_pricing_bps)s, %(recommended_tenor_years)s)
                RETURNING *
            """, values).fetchone()
            persist_compliance_result(
                connection, values["credit_request_number"], derived_payload,
                post_approval_exposure, compliance, required_authority,
            )
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="Credit request number already exists")
    return {**public_credit_request(row), "compliance": compliance}


@router.get("/api/requests/{credit_request_number}/compliance-score")
def get_credit_request_compliance(credit_request_number: str, _: dict = Depends(current_user)):
    with db_connection() as connection:
        row = connection.execute("""
            SELECT overall_score, compliance_status, category_scores,
                   findings, breached_rules, recommendations
            FROM credit_request_compliance
            WHERE credit_request_number = %s
        """, (credit_request_number.upper(),)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Compliance score not found for this credit request")
    return {
        "overallScore": float(row["overall_score"]),
        "complianceStatus": row["compliance_status"],
        "categoryScores": row["category_scores"],
        "findings": row["findings"],
        "breachedRules": row["breached_rules"],
        "recommendations": row["recommendations"],
    }
