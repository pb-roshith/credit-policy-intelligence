"""
Orchestration Service — pre-flight document selection and deal context optimization.

For each section:
1. Builds a section-specific deal context (only relevant fields)
2. Calls the orchestration agent with section-specific user prompt
3. Parses the agent's JSON response into OrchestrationResult
4. Returns strategy text that the section agent uses to guide its search

The orchestration agent is a single Mistral Agent (mistral-large-latest)
with a fixed system prompt. Only the user message changes per section.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.models.deal import Deal, Section
from app.telemetry import (
    extract_usage_metrics,
    get_tracer,
    set_gen_ai_attributes,
    set_span_attributes,
)
from app.prompt_canary import PromptCanary, enforce_canary
from app.response_entropy import enforce_response_entropy
from app.response_language import enforce_expected_language

logger = logging.getLogger(__name__)


# ── Orchestration Result ───────────────────────────────────────────

@dataclass
class OrchestrationResult:
    """Structured result from the orchestration agent."""
    recommended_documents: list[dict[str, str]] = field(default_factory=list)
    priority_data_points: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    confidence: float = 0.0
    gaps: list[str] = field(default_factory=list)
    strategy_summary: str = ""
    elapsed_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def to_strategy_text(self) -> str:
        """
        Convert to a text block that gets injected into the section agent's user prompt.
        This tells the agent what to search for and what to prioritize.
        """
        parts = []

        if self.strategy_summary:
            parts.append(f"### Strategy\n{self.strategy_summary}")

        if self.recommended_documents:
            doc_lines = ["| Priority | Document | Relevance |", "|---|---|---|"]
            for doc in self.recommended_documents:
                title = doc.get("title", "Unknown")
                relevance = doc.get("relevance", "").replace('\n', ' ')
                priority = doc.get("priority", "medium").upper()
                doc_lines.append(f"| **{priority}** | {title} | {relevance} |")
            parts.append("### Recommended Documents\n" + "\n".join(doc_lines))

        if self.priority_data_points:
            pt_lines = ["| Data Point |", "|---|"]
            for pt in self.priority_data_points:
                pt_lines.append(f"| {pt} |")
            parts.append("### Priority Data Points to Extract\n" + "\n".join(pt_lines))

        if self.search_queries:
            q_lines = ["| Query |", "|---|"]
            for q in self.search_queries:
                q_lines.append(f"| {q} |")
            parts.append("### Suggested Search Queries\n" + "\n".join(q_lines))

        if self.gaps:
            gap_lines = ["| Gap |", "|---|"]
            for gap in self.gaps:
                gap_lines.append(f"| {gap} |")
            parts.append("### Known Data Gaps (Mark with [Data not available])\n" + "\n".join(gap_lines))

        return "\n\n".join(parts) if parts else ""


# ── Section → Deal Fields Mapping ──────────────────────────────────
# Each section only gets the deal fields it actually needs.
# This reduces token waste by 40-60% on sections that don't need all fields.

SECTION_DEAL_FIELDS: dict[str, list[str]] = {
    "executive_summary": [
        "customer", "customer_type", "industry", "segment", "geography",
        "sector", "kyc", "facility", "currency", "amount", "tenure",
        "pricing", "repayment", "collateral", "due", "status",
    ],
    "client_overview": [
        "customer", "customer_type", "industry", "segment", "geography",
        "city", "sector", "kyc",
    ],
    "relationship_summary": [
        "customer", "customer_type", "facility", "currency", "amount",
        "tenure", "pricing",
    ],
    "industry_analysis": [
        "customer", "industry", "segment", "sector", "geography",
    ],
    "financial_analysis": [
        "customer", "industry", "currency", "amount", "sector",
    ],
    "ratio_analysis": [
        "customer", "industry", "currency", "sector",
    ],
    "cash_flow_analysis": [
        "customer", "industry", "currency", "amount", "tenure",
        "facility",
    ],
    "qualitative_assessment": [
        "customer", "customer_type", "industry", "segment", "geography",
        "sector",
    ],
    "credit_risk_assessment": [
        "customer", "industry", "segment", "sector", "facility",
        "currency", "amount", "tenure", "collateral",
    ],
    "facility_structure": [
        "customer", "facility", "currency", "amount", "tenure",
        "pricing", "repayment", "collateral", "due",
    ],
    "policy_mapping": [
        "customer", "segment", "facility", "currency", "amount",
        "tenure", "collateral",
    ],
    "collateral_and_security": [
        "customer", "collateral", "facility", "amount", "currency",
    ],
    "covenants_and_conditions": [
        "customer", "facility", "amount", "currency", "tenure",
    ],
    "esg_analysis": [
        "customer", "industry", "sector", "geography",
    ],
    "key_risks_and_mitigants": [
        "customer", "industry", "segment", "sector", "facility",
        "currency", "amount",
    ],
    "appendix": [
        "customer",
    ],
}

# ── Human-readable labels for deal fields ──────────────────────────

_FIELD_LABELS: dict[str, str] = {
    "customer": "Customer",
    "customer_type": "Customer Type",
    "industry": "Industry",
    "segment": "Segment",
    "geography": "Geography",
    "city": "City",
    "sector": "Sector",
    "kyc": "KYC Status",
    "facility": "Facility Type",
    "currency": "Currency",
    "amount": "Amount",
    "tenure": "Tenure",
    "pricing": "Pricing",
    "repayment": "Repayment",
    "collateral": "Collateral",
    "due": "Due Date",
    "status": "Deal Status",
}


class OrchestrationService:
    """Pre-flight document selection and deal context optimization."""

    @staticmethod
    def build_deal_context_for_section(deal: Deal, section_key: str) -> str:
        """
        Build a deal context string containing ONLY the fields relevant
        to this section. Reduces token waste significantly.

        Args:
            deal: The Deal ORM object
            section_key: e.g. "executive_summary"

        Returns:
            Formatted deal context string
        """
        fields = SECTION_DEAL_FIELDS.get(section_key)
        if not fields:
            # Fallback: include all core fields
            fields = list(SECTION_DEAL_FIELDS["executive_summary"])

        lines = ["--- Deal Context ---"]
        for f in fields:
            value = getattr(deal, f, None)
            if value is None or value == "":
                continue

            label = _FIELD_LABELS.get(f, f.replace("_", " ").title())

            # Format special fields
            if f == "amount":
                lines.append(f"{label}: {deal.currency} {value:,.0f}")
            elif f == "tenure":
                lines.append(f"{label}: {value} months")
            elif f == "collateral":
                lines.append(f"{label}: {'Secured' if value else 'Clean/Unsecured'}")
            else:
                lines.append(f"{label}: {value}")

        lines.append("---")
        return "\n".join(lines)

    @staticmethod
    async def select_documents_for_section(
        deal: Deal,
        section: Section,
        document_summaries: str,
        orch_agent_id: str | None,
    ) -> OrchestrationResult:
        """
        Run the orchestration agent to select documents for a section.

        1. Build section-specific deal context
        2. Build section-specific user prompt
        3. Call orchestration agent (Mistral Agent with fixed system prompt)
        4. Parse JSON response into OrchestrationResult

        Args:
            deal: The Deal ORM object
            section: The Section ORM object
            document_summaries: MCP document summaries (raw text)
            orch_agent_id: Mistral Agent ID for the orchestration agent

        Returns:
            OrchestrationResult with ranked documents and strategy
        """
        if not settings.ORCHESTRATION_ENABLED:
            logger.info(f"Orchestration disabled — skipping for {section.section_key}")
            return OrchestrationResult(
                strategy_summary="Orchestration disabled. Use library search freely.",
                confidence=0.0,
            )

        if not orch_agent_id:
            logger.warning("No orchestration agent available — skipping orchestration")
            return OrchestrationResult(
                strategy_summary="No orchestration agent. Use library search freely.",
                confidence=0.0,
            )

        # Check if we have any summaries to work with
        no_summaries = (
            not document_summaries
            or document_summaries.startswith(("Error:", "MCP", "No summaries"))
        )
        if no_summaries:
            logger.info(
                f"No MCP summaries available for {deal.customer} — "
                f"skipping orchestration for {section.section_key}"
            )
            return OrchestrationResult(
                strategy_summary=(
                    "No external document summaries available. "
                    "Search the document library for all relevant data."
                ),
                confidence=0.0,
            )

        start = time.time()
        tracer = get_tracer()

        # Build prompts
        from app.agents.orchestration_prompts import build_orchestration_user_prompt
        deal_context = OrchestrationService.build_deal_context_for_section(
            deal, section.section_key
        )
        user_prompt = build_orchestration_user_prompt(
            section_key=section.section_key,
            deal_context=deal_context,
            document_summaries=document_summaries,
        )
        prompt_canary = PromptCanary.create()
        user_prompt += prompt_canary.instruction

        # Call orchestration agent
        try:
            from app.services.mistral_library_service import _get_client, _call_with_retry

            client = _get_client()
            response = await _call_with_retry(
                lambda: client.agents.complete_async(
                    agent_id=orch_agent_id,
                    messages=[{"role": "user", "content": user_prompt}],
                ),
                description=f"Orchestration for '{section.section_key}'",
            )

            # Extract content
            content = None
            if getattr(response.choices[0], "message", None):
                content = response.choices[0].message.content
            elif (getattr(response.choices[0], "messages", None)
                  and len(response.choices[0].messages) > 0):
                content = response.choices[0].messages[-1].content

            if not content:
                logger.warning(f"Orchestration returned empty for {section.section_key}")
                return OrchestrationResult(
                    strategy_summary="Orchestration returned no strategy. Search freely.",
                    elapsed_ms=(time.time() - start) * 1000,
                )

            # Normalize content (may be list of content blocks)
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        parts.append(part["text"])
                    elif hasattr(part, "text"):
                        parts.append(part.text)
                    else:
                        parts.append(str(part))
                content = "\n".join(parts)

            enforce_canary(
                content,
                prompt_canary,
                context=f"orchestration:{section.section_key}",
            )
            enforce_response_entropy(
                content,
                context=f"orchestration:{section.section_key}",
            )
            enforce_expected_language(
                content,
                context=f"orchestration:{section.section_key}",
            )

            # Parse JSON response
            result = OrchestrationService._parse_orchestration_response(content)
            result.elapsed_ms = (time.time() - start) * 1000
            usage = extract_usage_metrics(response)
            result.input_tokens = usage["input_tokens"]
            result.output_tokens = usage["output_tokens"]
            result.total_tokens = usage["total_tokens"]

            doc_names = [doc.get("title", "Unknown") for doc in result.recommended_documents]

            # Record orchestration result in telemetry span
            if tracer:
                with tracer.start_as_current_span("orchestration_select_documents") as span:
                    set_span_attributes(span,
                        operation="orchestration_select_documents",
                        section_key=section.section_key,
                        customer=deal.customer or "",
                        confidence=str(result.confidence),
                        documents_recommended=str(len(result.recommended_documents)),
                        elapsed_ms=str(round(result.elapsed_ms)),
                        input_tokens=str(result.input_tokens),
                        output_tokens=str(result.output_tokens),
                        total_tokens=str(result.total_tokens),
                    )
                    set_gen_ai_attributes(span, system="mistral")

            logger.info(
                f"Orchestration for {section.section_key}: "
                f"{len(result.recommended_documents)} docs recommended: {doc_names}, "
                f"confidence={result.confidence:.2f}, "
                f"elapsed={result.elapsed_ms:.0f}ms\n"
                f"Complete Agent Output:\n{content}"
            )
            return result

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.warning(
                f"Orchestration failed for {section.section_key} "
                f"(elapsed={elapsed:.0f}ms): {e}"
            )
            return OrchestrationResult(
                strategy_summary=(
                    f"Orchestration failed ({type(e).__name__}). "
                    "Search the document library for all relevant data."
                ),
                confidence=0.0,
                elapsed_ms=elapsed,
            )

    @staticmethod
    def _parse_orchestration_response(raw: str) -> OrchestrationResult:
        """Parse the orchestration agent's JSON response."""
        import re

        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()

        # Try to extract JSON from the response
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    logger.warning("Could not parse orchestration JSON")
                    return OrchestrationResult(
                        strategy_summary=raw[:500],
                        confidence=0.0,
                    )
            else:
                # Treat entire response as strategy text
                return OrchestrationResult(
                    strategy_summary=raw[:500],
                    confidence=0.0,
                )

        return OrchestrationResult(
            recommended_documents=data.get("recommended_documents", []),
            priority_data_points=data.get("priority_data_points", []),
            search_queries=data.get("search_queries", []),
            confidence=float(data.get("confidence", 0.0)),
            gaps=data.get("gaps", []),
            strategy_summary=data.get("strategy_summary", ""),
        )
