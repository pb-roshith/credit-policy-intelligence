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
    from .dashboard import dashboard
    snapshot=dashboard(_)
    return {**snapshot['metrics'],'knowledge_fingerprint':snapshot['knowledge_fingerprint']}

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
    from ..services.current_knowledge import current_reviews
    from ..services.semantic_matching import load_matcher
    fingerprint=load_matcher().fingerprint
    with db_connection() as db:
        saved=db.execute('''SELECT DISTINCT ON (user_id,COALESCE(source_request_id,credit_request_number))
            user_id AS account_user_id,COALESCE(source_request_id,credit_request_number) AS request_id,review
            FROM ai_compliance_reviews ORDER BY user_id,COALESCE(source_request_id,credit_request_number),created_at DESC,review_id DESC''').fetchall()
    by_request={(r['account_user_id'],r['request_id']):r['review'] for r in current_reviews(saved,fingerprint)}
    result = []
    for row in rows:
        item = public_credit_request(row)
        item['account_user_id'] = row['account_user_id']
        assessment=by_request.get((row['account_user_id'],row.get('shared_deal_id') or row['credit_request_number']))
        item['compliance_score']=assessment.get('overall_score') if assessment else None
        item['compliance_status']=assessment.get('compliance_status') if assessment else 'Not assessed'
        item['assessment_scope']='current-semantic-graph' if assessment else None
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
    from ..services.compliance_agent import latest_stored_compliance_review
    review=latest_stored_compliance_review(credit_request_number,user=_)
    if not review:raise HTTPException(404,'Run a knowledge graph assessment for this request.')
    return {'overallScore':review.get('overall_score'),'complianceStatus':review['compliance_status'],
        'categoryScores':{},'findings':review['findings'],'breachedRules':[f for f in review['findings'] if f['result']=='Breach'],
        'recommendations':review.get('recommendations',[])}
