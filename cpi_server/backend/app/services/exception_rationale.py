import json
import math
from time import sleep

from fastapi import HTTPException
from app.ai_provider import AIClient as Mistral
from mistralai.client.utils import BackoffStrategy, RetryConfig

from ..config import MISTRAL_API_KEY, MISTRAL_POLICY_MODEL, MISTRAL_TIMEOUT_MS
from ..manufacture_data.policy_generation_service import _json_object
from ..telemetry import observe_ai


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


def pending_exception_rationale(exception: dict) -> dict:
    """Preserve the submission without representing fallback text as AI analysis."""
    return {
        "generation_status": "pending",
        "generation_notice": "Exception saved. AI rationale is pending because the AI service is busy. Analyst review is required.",
        "why_detected": "Submitted exception: " + str(exception.get("description") or "No description supplied."),
        "business_justification": "Not yet assessed. The analyst must review the submitted business justification.",
        "risk_implication": "Not yet assessed. AI risk analysis is unavailable.",
        "recommended_remediation": "Analyst review is required to determine remediation and monitoring actions.",
        "escalation_required": "Credit analyst approval is required. Further escalation has not been assessed.",
    }


def _review_context(review: dict | None, exception: dict) -> dict:
    """Send bounded relevant evidence, never full assessment input/provenance trees."""
    review = review or {}
    fields = ('rule_name', 'policy_clause', 'policy_type', 'result', 'severity',
              'actual', 'expected_condition', 'threshold', 'rationale', 'evidence')
    clause = str(exception.get('clause') or '').strip().casefold()
    findings = review.get('findings') or []
    matching = [finding for finding in findings if clause and any(
        clause in str(finding.get(key) or '').casefold()
        for key in ('policy_clause', 'rule_name', 'clause_code'))]
    selected = matching or [finding for finding in findings if str(
        finding.get('result') or finding.get('severity') or '').upper() in ('WARNING', 'BREACH')]
    return {
        'executive_summary': str(review.get('executive_summary') or '')[:1600],
        'findings': [{key: str(finding[key])[:800] for key in fields if finding.get(key) is not None}
                     for finding in selected[:4]],
        'findings_in_saved_review': len(findings),
        'context_note': 'Only selected findings are included. Text may be shortened; do not infer missing evidence.',
        'recommendations': [str(item)[:400] for item in (review.get('recommendations') or [])[:3]],
    }


def _retry_delay(error: Exception, attempt: int) -> float:
    response = getattr(error, 'raw_response', None)
    value = getattr(response, 'headers', {}).get('Retry-After')
    fallback = 10 * (2 ** attempt)
    try:
        delay = float(value)
    except (TypeError, ValueError):
        return fallback
    return delay if math.isfinite(delay) and delay >= 0 else fallback


def generate_exception_rationale(proposal: dict, exception: dict, compliance_review: dict | None, user_id: str) -> dict:
    if not MISTRAL_API_KEY:
        raise HTTPException(status_code=503, detail="MISTRAL_API_KEY is not configured")

    review_context = _review_context(compliance_review, exception)
    proposal_context = {key: proposal[key] for key in (
        'credit_request_number', 'borrower_name', 'industry', 'facility', 'rating',
        'currency', 'exposure', 'requested_amount', 'status') if key in proposal}
    prompt = f"""
You are a bank credit-policy exception analyst. Based only on the supplied credit proposal,
the user's exception description, and the saved compliance review, prepare a concise rationale
for an exception workflow. Do not invent financial values, policy limits, commitments, or approvals.

Credit proposal:
{json.dumps(proposal_context, default=str)}

Exception submitted by the user:
{json.dumps(exception, default=str)}

Saved compliance review:
{json.dumps(review_context, default=str)}

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
        with observe_ai(
            "Exception Management", "exception_rationale", user_id,
            str(proposal.get("credit_request_number", "")) or None,
            input_payload=prompt,
            retrieved_sources=["Credit proposal", "Submitted exception", "Saved compliance review"],
        ) as telemetry:
            with Mistral(api_key=MISTRAL_API_KEY, timeout_ms=MISTRAL_TIMEOUT_MS) as client:
                for attempt in range(3):
                    try:
                        response = client.chat.complete(
                            model=MISTRAL_POLICY_MODEL,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.1,
                            max_tokens=1200,
                            response_format={"type": "json_object"},
                            retries=RetryConfig('none', BackoffStrategy(0, 0, 1, 0), False),
                        )
                        break
                    except Exception as error:
                        if getattr(error, "status_code", None) != 429 or attempt == 2:
                            raise
                        delay = _retry_delay(error, attempt)
                        # Longer provider cooldowns should not hold the creation
                        # request open beyond the browser's request timeout.
                        if delay > 30:
                            raise
                        sleep(delay)
            telemetry["response"] = response
        generated = _json_object(_chat_response_text(response))
    except Exception as error:
        if getattr(error, "status_code", None) == 429:
            return pending_exception_rationale(exception)
        raise HTTPException(status_code=502, detail=f"Mistral exception rationale generation failed: {error}") from error

    required = ("why_detected", "business_justification", "risk_implication", "recommended_remediation", "escalation_required")
    rationale = {key: str(generated.get(key, "")).strip() for key in required}
    if not all(rationale.values()):
        raise HTTPException(status_code=502, detail="Mistral returned an incomplete exception rationale")
    return rationale
