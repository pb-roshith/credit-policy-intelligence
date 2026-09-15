import json

from fastapi import HTTPException
from mistralai.client import Mistral

from ..config import MISTRAL_API_KEY, MISTRAL_POLICY_MODEL
from ..manufacture_data.policy_generation_service import _json_object


def _chat_response_text(response) -> str:
    """Extract text from a Mistral ChatCompletionResponse."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            chunk.get("text", "") if isinstance(chunk, dict) else getattr(chunk, "text", "")
            for chunk in content
        ).strip()
    return str(content or "").strip()


def generate_exception_rationale(proposal: dict, exception: dict, compliance_review: dict | None) -> dict:
    if not MISTRAL_API_KEY:
        raise HTTPException(status_code=503, detail="MISTRAL_API_KEY is not configured")

    review_context = {
        "executive_summary": (compliance_review or {}).get("executive_summary"),
        "findings": (compliance_review or {}).get("findings", []),
        "recommendations": (compliance_review or {}).get("recommendations", []),
    }
    prompt = f"""
You are a bank credit-policy exception analyst. Based only on the supplied credit proposal,
the user's exception description, and the saved compliance review, prepare a concise rationale
for an exception workflow. Do not invent financial values, policy limits, commitments, or approvals.

Credit proposal:
{json.dumps(proposal, default=str, indent=2)}

Exception submitted by the user:
{json.dumps(exception, default=str, indent=2)}

Saved compliance review:
{json.dumps(review_context, default=str, indent=2)}

Return only valid JSON with exactly these string fields:
{{
  "why_detected": "explain why the described issue is an exception",
  "business_justification": "explain the credible business purpose, clearly flagging missing support",
  "risk_implication": "explain the relevant credit and policy risks",
  "recommended_remediation": "give specific monitoring or remediation actions",
  "escalation_required": "state whether escalation is needed and to which authority if supported"
}}
""".strip()
    try:
        with Mistral(api_key=MISTRAL_API_KEY) as client:
            response = client.chat.complete(
                model=MISTRAL_POLICY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
        generated = _json_object(_chat_response_text(response))
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Mistral exception rationale generation failed: {error}") from error

    required = ("why_detected", "business_justification", "risk_implication", "recommended_remediation", "escalation_required")
    rationale = {key: str(generated.get(key, "")).strip() for key in required}
    if not all(rationale.values()):
        raise HTTPException(status_code=502, detail="Mistral returned an incomplete exception rationale")
    return rationale
