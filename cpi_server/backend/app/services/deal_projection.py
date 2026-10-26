"""Derived CPI compliance projection of a canonical shared deal."""
from fastapi import HTTPException
from psycopg.errors import UniqueViolation
from ..config import GEOGRAPHY_RISK
from ..database import db_connection, resolve_borrower, retry_on_db_conflict
from ..schemas import CreateCreditRequest, MAX_SAFE_MONETARY_AMOUNT
from .compliance_scoring import calculate_compliance_score, persist_compliance_result, public_credit_request

@retry_on_db_conflict
def persist_deal_projection(payload: CreateCreditRequest, shared_deal_id: str):
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
            existing = connection.execute("SELECT * FROM credit_requests WHERE shared_deal_id = %s", (shared_deal_id,)).fetchone()
            if existing:
                return public_credit_request(existing)
            values["shared_deal_id"] = shared_deal_id
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
            if values["exposure"] < 0 or values["exposure"] > MAX_SAFE_MONETARY_AMOUNT:
                raise HTTPException(status_code=422, detail="The calculated exposure is outside the supported range")
            post_approval_exposure = values["exposure"] + values["requested_amount"]
            if post_approval_exposure > MAX_SAFE_MONETARY_AMOUNT:
                raise HTTPException(status_code=422, detail="The resulting exposure exceeds the supported maximum")
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
            adjusted_collateral = round(post_approval_exposure * payload.collateral_coverage / 100)
            if adjusted_collateral > MAX_SAFE_MONETARY_AMOUNT:
                raise HTTPException(status_code=422, detail="The calculated collateral exceeds the supported maximum")
            derived_payload = CreateCreditRequest.model_validate({**payload.model_dump(), **{
                "geography_risk": geography_risk,
                "concentration_limit_utilization": concentration_utilization,
                "adjusted_collateral": adjusted_collateral,
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
                    shared_deal_id, credit_request_number, borrower_id, borrower_name, industry, geography, exposure, facility,
                    rating, requested_amount, status, compliance_score
                    , collateral_coverage, recommended_pricing_bps, recommended_tenor_years
                ) VALUES (%(shared_deal_id)s, %(credit_request_number)s, %(borrower_id)s, %(borrower_name)s, %(industry)s, %(geography)s,
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


