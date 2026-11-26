from fastapi import APIRouter, Depends, HTTPException
from app.ai_provider import AIClient as Mistral
from ..access_control import has_permission
from ..config import MISTRAL_API_KEY, MISTRAL_TIMEOUT_MS, MISTRAL_POLICY_MODEL
from ..database import account_user_id, db_connection
from ..manufacture_data.policy_generation_service import _json_object
from ..schemas import ComplianceCopilotRequest, ComplianceReviewRequest
from ..security import current_user
from ..services.compliance_agent import latest_stored_compliance_review
from ..telemetry import observe_ai
from ..services.assessment_request import normalize_request_id
from ..services.compliance_copilot import copilot_prompt
from ..services.exception_rationale import _chat_response_text, _retry_delay
from mistralai.client.utils import BackoffStrategy, RetryConfig
from time import sleep

router = APIRouter()

@router.get('/api/compliance-review/{credit_request_number}/assessment-graph')
def request_assessment_graph(credit_request_number: str, review_id: int, user: dict = Depends(current_user)):
    from ..services.assessment_paths import assessment_graph
    from ..services.current_knowledge import current_review
    request_id = normalize_request_id(credit_request_number)
    owner = account_user_id.get() or user['user_id']
    with db_connection() as db:
        saved = db.execute("""
            SELECT review FROM ai_compliance_reviews
            WHERE user_id=%s AND review_id=%s AND COALESCE(source_request_id,credit_request_number)=%s
        """, (owner, review_id, request_id)).fetchone()
        if not saved or not current_review(saved['review']):
            raise HTTPException(404, 'This assessment is unavailable for the selected request.')
        review = saved['review']
        exceptions = []
        if has_permission(user, 'exceptions.read'):
            exceptions = db.execute("""
                SELECT exception_id AS id,status,rationale FROM credit_request_exceptions
                WHERE user_id=%s AND COALESCE(source_request_id,credit_request_number)=%s
                  AND rationale->'knowledge_context'->>'knowledge_fingerprint'=%s
                ORDER BY exception_id
            """, (owner, request_id, review['knowledge_fingerprint'])).fetchall()
    return assessment_graph(review, exceptions)


@router.get('/api/compliance-review/{credit_request_number}/policy-mapping')
def request_policy_mapping(credit_request_number: str,user: dict = Depends(current_user)):
    from ..services.policy_mapping_cache import get_request_policy_mapping
    return get_request_policy_mapping(credit_request_number, user)

@router.post('/api/compliance-review/applicability')
def check_applicability(payload: ComplianceReviewRequest,user: dict = Depends(current_user)):
    if not has_permission(user, "compliance.execute"):
        raise HTTPException(403, "Compliance execution is unavailable")
    from ..services.rule_assessment import assessment_request_context
    from ..services.semantic_matching import load_matcher
    request_id,data=assessment_request_context(payload.credit_request_number,user)
    report=load_matcher().match(data)
    return {'request_id':request_id,**report}

@router.get('/api/compliance-review/current-summaries')
def current_assessment_summaries(user:dict=Depends(current_user)):
    from ..services.current_knowledge import current_reviews
    from ..services.semantic_matching import load_matcher
    with db_connection() as db:
        rows=db.execute("""SELECT DISTINCT ON (user_id,COALESCE(source_request_id,credit_request_number))
            user_id AS account_user_id,COALESCE(source_request_id,credit_request_number) AS request_id,review
            FROM ai_compliance_reviews ORDER BY user_id,COALESCE(source_request_id,credit_request_number),created_at DESC,review_id DESC""").fetchall()
    return [{'request_id':r['request_id'],'account_user_id':r['account_user_id'],
        'compliance_score':r['review'].get('overall_score'),'compliance_status':r['review'].get('compliance_status'),
        'assessment_scope':'current-semantic-graph'} for r in current_reviews(rows,load_matcher().fingerprint)]


@router.get("/api/compliance-review/{credit_request_number}/latest")
def get_latest_compliance_review(credit_request_number: str, _: dict = Depends(current_user)):
    review = latest_stored_compliance_review(credit_request_number, user=_)
    if not review:
        raise HTTPException(status_code=404, detail="No saved compliance review was found for this credit request")
    return review


@router.get("/api/compliance-review/history/{review_id}")
def historical_review(review_id: int, user: dict = Depends(current_user)):
    with db_connection() as connection:
        row=connection.execute("SELECT review_id,review,created_at FROM ai_compliance_reviews WHERE review_id=%s",(review_id,)).fetchone()
    if not row:raise HTTPException(404,"Assessment version not found in your account")
    from ..services.current_knowledge import current_review
    if not current_review(row['review']):raise HTTPException(410,'Run a current knowledge graph assessment for this request.')
    from ..services.assessment_comparison import refresh_finding_comparisons
    return refresh_finding_comparisons({**row['review'],"review_id":row['review_id'],"stored_at":row['created_at'],"cached":True})


@router.post("/api/compliance-review/run")
def run_compliance_review(payload: ComplianceReviewRequest, user: dict = Depends(current_user)):
    if not has_permission(user, "compliance.execute"):
        raise HTTPException(403, "Compliance execution is unavailable")
    from ..services.semantic_assessment import run_rule_assessment
    review = run_rule_assessment(normalize_request_id(payload.credit_request_number), user["user_id"], user=user)
    review["cached"] = False
    return review


@router.post("/api/compliance-review/copilot")
def compliance_review_copilot(payload: ComplianceCopilotRequest, user: dict = Depends(current_user)):
    if not MISTRAL_API_KEY:
        raise HTTPException(status_code=503, detail="MISTRAL_API_KEY is not configured")
    review = latest_stored_compliance_review(payload.credit_request_number, user=user)
    if not review:
        raise HTTPException(status_code=404, detail="Run the Compliance Review Agent before asking the copilot")
    prompt = copilot_prompt(review, payload.question)
    try:
        with observe_ai(
            "Compliance Review", "compliance_copilot", user["user_id"],
            normalize_request_id(payload.credit_request_number), input_payload=prompt,
            retrieved_sources=["AI Compliance Findings", "Compliance review metadata"],
        ) as telemetry:
            with Mistral(api_key=MISTRAL_API_KEY, timeout_ms=min(MISTRAL_TIMEOUT_MS, 30000)) as client:
                for attempt in range(2):
                    try:
                        response = client.chat.complete(
                            model=MISTRAL_POLICY_MODEL,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.1, max_tokens=1200,
                            response_format={"type": "json_object"},
                            retries=RetryConfig('none', BackoffStrategy(0, 0, 1, 0), False),
                        )
                        break
                    except Exception as error:
                        delay = _retry_delay(error, attempt)
                        if getattr(error, 'status_code', None) != 429 or attempt or delay > 30:
                            raise
                        sleep(delay)
            telemetry["response"] = response
        answer = _json_object(_chat_response_text(response)).get("answer", "")
    except Exception as error:
        if getattr(error, 'status_code', None) == 429:
            raise HTTPException(429, "Compliance Copilot is temporarily rate-limited. Please try again in a minute.") from error
        raise HTTPException(status_code=502, detail="Compliance Copilot could not complete the AI request. Please try again.") from error
    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(status_code=502, detail="Compliance Copilot returned an empty answer")
    return {
        "answer": answer.strip(),
        "credit_request_number": normalize_request_id(payload.credit_request_number),
        "generated_by": "Mistral Credit Compliance Review Agent",
        "user": user["user_id"],
    }
