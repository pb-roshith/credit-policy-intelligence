import json
from fastapi import APIRouter, Depends, HTTPException
from mistralai.client import Mistral
from ..config import MISTRAL_API_KEY, MISTRAL_TIMEOUT_MS
from ..database import db_connection
from ..manufacture_data.policy_generation_service import _json_object, _response_text
from ..schemas import ComplianceCopilotRequest, ComplianceReviewRequest
from ..security import current_user
from ..services.compliance_agent import GenerativeComplianceReviewAgent, latest_stored_compliance_review
from ..telemetry import observe_ai
from ..services.assessment_request import normalize_request_id

router = APIRouter()

@router.get('/api/compliance-review/{credit_request_number}/policy-mapping')
def request_policy_mapping(credit_request_number: str,user: dict = Depends(current_user)):
    from ..services.policy_mapping_cache import get_request_policy_mapping
    return get_request_policy_mapping(credit_request_number, user)

@router.post('/api/compliance-review/applicability')
def check_applicability(payload: ComplianceReviewRequest,user: dict = Depends(current_user)):
    from ..services.rule_assessment import assessment_request_context,active_rule_candidates
    from ..services.policy_scope import policy_first_applicability
    request_id,data=assessment_request_context(payload.credit_request_number,user)
    from datetime import date
    candidates=active_rule_candidates(date.today())
    report=policy_first_applicability(data,candidates,data.get('status'))
    return {'request_id':request_id,**report}

@router.get("/api/compliance-review/{credit_request_number}/latest")
def get_latest_compliance_review(credit_request_number: str, _: dict = Depends(current_user)):
    review = latest_stored_compliance_review(credit_request_number)
    if not review:
        raise HTTPException(status_code=404, detail="No saved compliance review was found for this credit request")
    return review


@router.get("/api/compliance-review/history/{review_id}")
def historical_review(review_id: int, user: dict = Depends(current_user)):
    with db_connection() as connection:
        row=connection.execute("SELECT review_id,review,created_at FROM ai_compliance_reviews WHERE review_id=%s",(review_id,)).fetchone()
    if not row:raise HTTPException(404,"Assessment version not found in your account")
    return {**row['review'],"review_id":row['review_id'],"stored_at":row['created_at'],"cached":True}


@router.post("/api/compliance-review/run")
def run_compliance_review(payload: ComplianceReviewRequest, user: dict = Depends(current_user)):
    from ..services.rule_assessment import run_rule_assessment
    review = run_rule_assessment(normalize_request_id(payload.credit_request_number), user["user_id"], user=user)
    review["cached"] = False
    return review


@router.post("/api/compliance-review/copilot")
def compliance_review_copilot(payload: ComplianceCopilotRequest, user: dict = Depends(current_user)):
    if not MISTRAL_API_KEY:
        raise HTTPException(status_code=503, detail="MISTRAL_API_KEY is not configured")
    with db_connection() as connection:
        stored = connection.execute("""
            SELECT review, agent_id
            FROM ai_compliance_reviews
            WHERE COALESCE(source_request_id, credit_request_number) = %s
            ORDER BY created_at DESC, review_id DESC LIMIT 1
        """, (normalize_request_id(payload.credit_request_number),)).fetchone()
    if not stored:
        raise HTTPException(status_code=404, detail="Run the Compliance Review Agent before asking the copilot")
    review = stored["review"]
    prompt = f"""
You are Compliance Copilot. Answer the user's question only from the AI Compliance Findings table
and review metadata supplied below. Do not use outside facts, invent evidence, or change a finding's
classification. If the table does not contain enough information, say so clearly.

Review metadata:
{json.dumps({key: review.get(key) for key in ('overall_score', 'compliance_status', 'executive_summary', 'recommendations')}, default=str)}

AI Compliance Findings table:
{json.dumps(review.get('findings', []), default=str)}

User question: {payload.question}

Return only valid JSON: {{"answer":"clear, concise answer grounded in the table"}}
""".strip()
    try:
        with observe_ai(
            "Compliance Review", "compliance_copilot", user["user_id"],
            normalize_request_id(payload.credit_request_number), input_payload=prompt,
            retrieved_sources=["AI Compliance Findings", "Compliance review metadata"],
        ) as telemetry:
            with Mistral(api_key=MISTRAL_API_KEY, timeout_ms=MISTRAL_TIMEOUT_MS) as client:
                response = client.beta.conversations.start(
                    agent_id=GenerativeComplianceReviewAgent()._agent_id(), inputs=prompt, store=False,
                )
            telemetry["response"] = response
        answer = str(_json_object(_response_text(response)).get("answer", "")).strip()
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Compliance Copilot failed: {error}") from error
    if not answer:
        raise HTTPException(status_code=502, detail="Compliance Copilot returned an empty answer")
    return {
        "answer": answer,
        "credit_request_number": normalize_request_id(payload.credit_request_number),
        "generated_by": "Mistral Credit Compliance Review Agent",
        "user": user["user_id"],
    }
