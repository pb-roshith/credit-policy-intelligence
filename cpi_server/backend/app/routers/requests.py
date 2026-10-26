from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from ..database import db_connection
from ..security import current_user
from ..services.compliance_scoring import public_credit_request

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
            SELECT user_id, borrower_id,
                   SUM(outstanding_exposure)::BIGINT AS exposure
            FROM latest_borrower_exposure
            GROUP BY user_id, borrower_id
        )
        SELECT cr.user_id AS account_user_id, cr.shared_deal_id, cr.credit_request_number, cr.borrower_id, cr.borrower_name, cr.industry, cr.geography,
               COALESCE(be.exposure, cr.exposure) AS exposure, cr.facility,
               cr.rating, cr.requested_amount, cr.status, cr.compliance_score,
               cr.collateral_coverage, cr.recommended_pricing_bps, cr.recommended_tenor_years
        FROM credit_requests cr
        LEFT JOIN borrower_exposure be ON be.borrower_id = cr.borrower_id AND be.user_id = cr.user_id
    """
    parameters: tuple = ()
    if status:
        query += " WHERE LOWER(cr.status) = LOWER(%s)"
        parameters = (status,)
    query += " ORDER BY cr.compliance_score ASC, cr.credit_request_number ASC"
    with db_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
    result = []
    for row in rows:
        item = public_credit_request(row)
        item['account_user_id'] = row['account_user_id']
        if _['role'] == 'credit_analyst' and row['account_user_id'] != _['user_id'] and not row.get('shared_deal_id'):
            item['credit_request_number'] += '@' + row['account_user_id']
        result.append(item)
    return result


@router.get("/api/deals")
def shared_deals(user: dict = Depends(current_user)):
    from ..services.deal_retrieval import DealRetrievalAgent
    return DealRetrievalAgent().run(user)


@router.post("/api/deals", deprecated=True)
@router.post("/api/requests", deprecated=True)
def create_shared_deal(payload: dict, user: dict = Depends(current_user)):
    raise HTTPException(403, "CPI is view-only for deals. Create new deals in Credit Dossier.")


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
