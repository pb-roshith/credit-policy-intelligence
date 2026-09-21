from datetime import datetime, timezone
import json
from fastapi import HTTPException
from mistralai.client import Mistral
from ..config import COMPLIANCE_AGENT_LOCK, MISTRAL_API_KEY, MISTRAL_POLICY_MODEL
from ..database import db_connection, shared_policy_connection
from ..manufacture_data.policy_generation_service import _json_object, _response_text
from ..telemetry import observe_ai

class GenerativeComplianceReviewAgent:
    """Use a Mistral agent with policy-library retrieval to classify a request."""

    POLICY_TYPES = [
        "Leverage", "Collateral", "Pricing", "Tenor", "Covenant", "Sector",
        "Delegation", "Rating", "Country", "Industry", "LTV", "DSCR",
        "Concentration", "Currency", "Duration", "Liquidity", "Underwriting",
        "Risk Appetite", "Regulatory Capital", "Special Assets & Recovery",
    ]
    STATUS_RANK = {"PASS": 0, "WARNING": 1, "BREACH": 2}

    def _agent_id(self) -> str:
        if not MISTRAL_API_KEY:
            raise HTTPException(status_code=503, detail="MISTRAL_API_KEY is not configured")
        with COMPLIANCE_AGENT_LOCK:
            with shared_policy_connection() as connection:
                configuration = connection.execute("""
                    SELECT mistral_library_id, mistral_compliance_agent_id
                    FROM policy_ai_configuration WHERE id = 1
                """).fetchone()
            if not configuration or not configuration["mistral_library_id"]:
                raise HTTPException(
                    status_code=503,
                    detail="Generate the policy library before running the Compliance Review Agent",
                )
            if configuration["mistral_compliance_agent_id"]:
                return configuration["mistral_compliance_agent_id"]
            try:
                with Mistral(api_key=MISTRAL_API_KEY) as client:
                    agent = client.beta.agents.create(
                        model=MISTRAL_POLICY_MODEL,
                        name="Credit Compliance Review Agent",
                        description="Reviews credit proposals against retrieved bank policy documents.",
                        instructions=(
                            "Act as an independent bank credit compliance reviewer. For every review, "
                            "search the attached policy library, compare only the supplied proposal facts "
                            "with retrieved requirements, and produce evidence-grounded JSON. Never invent "
                            "proposal facts, thresholds, clauses, or citations."
                        ),
                        tools=[{"type": "document_library", "library_ids": [configuration["mistral_library_id"]]}],
                        completion_args={"temperature": 0.1, "top_p": 0.9, "max_tokens": 12000},
                    )
            except Exception as error:
                raise HTTPException(status_code=502, detail=f"Could not create the Compliance Review Agent: {error}") from error
            with shared_policy_connection() as connection:
                connection.execute("""
                    UPDATE policy_ai_configuration
                    SET mistral_compliance_agent_id = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (agent.id,))
            return agent.id

    @staticmethod
    def _context(request_number: str) -> tuple[dict, list[dict], list[dict]]:
        with db_connection() as connection:
            proposal = connection.execute("""
                SELECT cr.credit_request_number, cr.borrower_name, cr.industry, cr.facility,
                       cr.rating, cr.requested_amount, cr.exposure, cr.status,
                       cc.geography_risk, cc.concentration_limit_utilization,
                       cc.adjusted_collateral, cc.post_approval_exposure,
                       cc.approval_authority, cc.total_required_documents,
                       cc.uploaded_required_documents
                FROM credit_requests cr
                JOIN credit_request_compliance cc
                  ON cc.credit_request_number = cr.credit_request_number
                WHERE cr.credit_request_number = %s
            """, (request_number,)).fetchone()
            signals = connection.execute("""
                SELECT clause_code, clause_name, result AS submitted_signal
                FROM credit_request_policy_evaluations
                WHERE credit_request_number = %s ORDER BY evaluation_id
            """, (request_number,)).fetchall()
        with shared_policy_connection() as connection:
            policies = connection.execute("""
                SELECT policy_id, library_policy_id, policy_code, title, clause_number,
                       policy_type, file_name
                FROM policy_documents
                WHERE library_policy_id IS NOT NULL
                ORDER BY display_order, policy_id
            """).fetchall()
        if not proposal:
            raise HTTPException(status_code=404, detail="Compliance data was not found for this credit request")
        if not policies:
            raise HTTPException(status_code=503, detail="The policy library is empty")
        return dict(proposal), [dict(item) for item in signals], [dict(item) for item in policies]

    @staticmethod
    def _prompt(proposal: dict, signals: list[dict], policies: list[dict]) -> str:
        catalog = "\n".join(
            f"- Policy ID {item['library_policy_id']}: {item['title']} | "
            f"type {item['policy_type']} | clause {item['clause_number']} | file {item['file_name']}"
            for item in policies
        )
        return f"""
You are the Credit Compliance Review Agent. Perform a fresh generative compliance review.

Mandatory method:
1. Use the document_library tool to retrieve every policy needed to assess the proposal.
2. Derive the applicable thresholds and required approvals from retrieved policy textâ€”not from hard-coded rules.
3. Compare the supplied proposal facts with that evidence and independently classify each material check.
4. Use BREACH only for a clear policy conflict, WARNING for ambiguity/near-limit/missing evidence, and PASS only when the facts clearly satisfy the retrieved requirement.
5. Do not invent missing proposal values. A submitted signal is an input assertion, not policy evidence; corroborate it against retrieved policy wherever the underlying metric is unavailable.
6. Every finding must cite exactly one Policy ID from the catalog and include a brief faithful evidence paraphrase.
7. Cover all materially relevant policy areas and include passing checks as well as warnings and breaches.

Credit proposal facts:
{json.dumps(proposal, default=str, indent=2)}

Submitted assessment signals:
{json.dumps(signals, default=str, indent=2)}

Policy catalog:
{catalog}

Return only valid JSON with this exact shape:
{{
  "overall_score": 0,
  "compliance_status": "short overall classification",
  "executive_summary": "concise explanation of the review",
  "findings": [
    {{
      "policy_id": "library Policy ID from catalog",
      "policy_clause": "clause reference and name",
      "actual": "proposal fact used",
      "threshold": "retrieved policy requirement",
      "variance": "plain-language comparison",
      "severity": "PASS or WARNING or BREACH",
      "rationale": "why the agent chose this classification",
      "evidence": "brief faithful paraphrase of retrieved policy evidence"
    }}
  ],
  "recommendations": ["specific evidence-grounded action"]
}}
overall_score must be an integer from 0 to 100. Do not return a finding without retrieved evidence.
""".strip()

    def run(self, request_number: str, user_id: str) -> dict:
        request_number = request_number.strip().upper()
        proposal, signals, policies = self._context(request_number)
        agent_id = self._agent_id()
        try:
            with observe_ai("Compliance Review", "compliance_agent", user_id, request_number) as telemetry:
                with Mistral(api_key=MISTRAL_API_KEY) as client:
                    response = client.beta.conversations.start(
                        agent_id=agent_id, inputs=self._prompt(proposal, signals, policies), store=False,
                    )
                telemetry["response"] = response
            generated = _json_object(_response_text(response))
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"Compliance Review Agent failed: {error}") from error

        policy_by_library_id = {str(item["library_policy_id"]): item for item in policies}
        findings = []
        for item in generated.get("findings", []):
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity", "")).strip().upper()
            source = policy_by_library_id.get(str(item.get("policy_id", "")).strip())
            if severity not in self.STATUS_RANK or not source:
                continue
            findings.append({
                "policy_type": source["policy_type"],
                "policy_clause": str(item.get("policy_clause") or source["title"]),
                "actual": str(item.get("actual") or "Not supplied"),
                "threshold": str(item.get("threshold") or "See cited policy"),
                "variance": str(item.get("variance") or "Agent assessment"),
                "severity": severity,
                "rationale": str(item.get("rationale") or "Classified from retrieved policy evidence."),
                "evidence": str(item.get("evidence") or "Relevant policy evidence retrieved."),
                "policy_id": source["policy_id"],
                "library_policy_id": source["library_policy_id"],
            })
        if not findings:
            raise HTTPException(status_code=502, detail="Compliance Review Agent returned no valid evidence-grounded findings")

        try:
            overall_score = max(0, min(100, int(round(float(generated["overall_score"])))))
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=502, detail="Compliance Review Agent returned an invalid overall score")
        counts = {status: sum(item["severity"] == status for item in findings) for status in self.STATUS_RANK}
        heat_status = {}
        for finding in findings:
            policy_type = finding["policy_type"]
            if policy_type not in heat_status or self.STATUS_RANK[finding["severity"]] > self.STATUS_RANK[heat_status[policy_type]]:
                heat_status[policy_type] = finding["severity"]
        result = {
            "agent": "Mistral Credit Compliance Review Agent",
            "model": MISTRAL_POLICY_MODEL,
            "credit_request": {
                "credit_request_number": proposal["credit_request_number"],
                "borrower_name": proposal["borrower_name"], "industry": proposal["industry"],
                "facility": proposal["facility"], "rating": proposal["rating"],
                "requested_amount": proposal["requested_amount"], "exposure": proposal["exposure"],
                "status": proposal["status"],
            },
            "overall_score": overall_score,
            "compliance_status": str(generated.get("compliance_status") or "AI review complete"),
            "executive_summary": str(generated.get("executive_summary") or "Review completed from retrieved policy evidence."),
            "findings": findings,
            "counts": counts,
            "heatmap": [
                {"policy_type": name, "severity": heat_status[name]}
                for name in self.POLICY_TYPES if name in heat_status
            ],
            "recommendations": [str(item) for item in generated.get("recommendations", []) if str(item).strip()],
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        with db_connection() as connection:
            stored = connection.execute("""
                INSERT INTO ai_compliance_reviews
                    (credit_request_number, agent_id, review, created_by)
                VALUES (%s, %s, %s::jsonb, %s) RETURNING review_id
            """, (request_number, agent_id, json.dumps(result), user_id)).fetchone()
        result["review_id"] = stored["review_id"]
        return result


def latest_stored_compliance_review(request_number: str) -> dict | None:
    with db_connection() as connection:
        stored = connection.execute("""
            SELECT review_id, review, created_at
            FROM ai_compliance_reviews
            WHERE credit_request_number = %s
            ORDER BY created_at DESC, review_id DESC LIMIT 1
        """, (request_number.strip().upper(),)).fetchone()
    if not stored:
        return None
    review = dict(stored["review"])
    review["review_id"] = stored["review_id"]
    review["stored_at"] = stored["created_at"]
    review["cached"] = True
    return review

