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

router = APIRouter()

@router.get("/api/compliance-review/{credit_request_number}/latest")
def get_latest_compliance_review(credit_request_number: str, _: dict = Depends(current_user)):
    review = latest_stored_compliance_review(credit_request_number)
    if not review:
        raise HTTPException(status_code=404, detail="No saved compliance review was found for this credit request")
    return review


@router.post("/api/compliance-review/run")
def run_compliance_review(payload: ComplianceReviewRequest, user: dict = Depends(current_user)):
    stored = latest_stored_compliance_review(payload.credit_request_number)
    if stored:
        return stored
    review = GenerativeComplianceReviewAgent().run(payload.credit_request_number, user["user_id"])
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
            WHERE credit_request_number = %s
            ORDER BY created_at DESC, review_id DESC LIMIT 1
        """, (payload.credit_request_number.strip().upper(),)).fetchone()
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
            payload.credit_request_number.strip().upper(), input_payload=prompt,
            retrieved_sources=["AI Compliance Findings", "Compliance review metadata"],
        ) as telemetry:
            with Mistral(api_key=MISTRAL_API_KEY, timeout_ms=MISTRAL_TIMEOUT_MS) as client:
                response = client.beta.conversations.start(
                    agent_id=stored["agent_id"], inputs=prompt, store=False,
                )
            telemetry["response"] = response
        answer = str(_json_object(_response_text(response)).get("answer", "")).strip()
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Compliance Copilot failed: {error}") from error
    if not answer:
        raise HTTPException(status_code=502, detail="Compliance Copilot returned an empty answer")
    return {
        "answer": answer,
        "credit_request_number": payload.credit_request_number.strip().upper(),
        "generated_by": "Mistral Credit Compliance Review Agent",
        "user": user["user_id"],
    }
