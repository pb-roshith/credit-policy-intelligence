"""Reusable Mistral agent for detailed, internally consistent manufactured data."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from mistralai.client import Mistral

from catalog import TABLE_COLUMNS, document_sections, document_summary
from settings import settings


logger = logging.getLogger("local_mcp.ai_generator")


def _conversation_text(response: Any) -> str:
    fragments: list[str] = []
    for output in getattr(response, "outputs", []) or []:
        if getattr(output, "type", None) != "message.output":
            continue
        content = getattr(output, "content", "")
        if isinstance(content, str):
            fragments.append(content)
        else:
            fragments.append(
                "".join(getattr(item, "text", "") for item in content)
            )
    return "\n".join(fragments).strip()


def _parse_json(value: str) -> Any:
    text = value.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


class ManufacturingAgent:
    """One temporary Mistral agent reused across an entire manufacturing job."""

    def __init__(self) -> None:
        self.client = (
            Mistral(api_key=settings.mistral_api_key)
            if settings.mistral_api_key
            else None
        )
        self.agent_id: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.client and self.agent_id)

    def __enter__(self) -> "ManufacturingAgent":
        if not self.client:
            logger.warning(
                "MISTRAL_API_KEY is unavailable; using detailed deterministic fallbacks."
            )
            return self
        try:
            agent = self.client.beta.agents.create(
                model="mistral-large-latest",
                name="Detailed Credit Data Manufacturer",
                description=(
                    "Temporary agent for internally consistent synthetic credit data."
                ),
                instructions=(
                    "Return valid JSON only. Never include markdown fences or prose "
                    "outside JSON. Use only the supplied synthetic borrower context. "
                    "Keep all identifiers and financial values internally consistent. "
                    "Never imply that the manufactured data is a real filing."
                ),
                completion_args={
                    "temperature": 0.25,
                    "max_tokens": 7000,
                    "response_format": {"type": "json_object"},
                },
            )
            self.agent_id = agent.id
        except Exception:
            logger.exception(
                "Could not create the manufacturing agent; using fallbacks."
            )
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.client and self.agent_id:
            try:
                self.client.beta.agents.delete(agent_id=self.agent_id)
            except Exception:
                logger.warning(
                    "Could not delete temporary manufacturing agent %s",
                    self.agent_id,
                    exc_info=True,
                )

    def generate_json(
        self,
        prompt: dict[str, object],
        fallback: dict[str, object],
    ) -> dict[str, object]:
        if not self.available or not self.client or not self.agent_id:
            return fallback
        for attempt in range(2):
            try:
                response = self.client.beta.conversations.start(
                    agent_id=self.agent_id,
                    inputs=json.dumps(prompt, default=str),
                    store=False,
                )
                result = _parse_json(_conversation_text(response))
                if isinstance(result, dict):
                    return result
            except Exception:
                logger.warning(
                    "Mistral manufacturing request failed on attempt %s",
                    attempt + 1,
                    exc_info=True,
                )
        return fallback

    def generate_context(
        self,
        fallback: dict[str, object],
    ) -> dict[str, object]:
        prompt = {
            "task": (
                "Expand this synthetic borrower master context with realistic and "
                "internally consistent credit details."
            ),
            "requiredKeys": list(fallback),
            "borrowerContext": fallback,
            "rules": [
                "Preserve company_name, industry and geography exactly.",
                "Preserve PAN, GSTIN and CIN formats and reuse them everywhere.",
                "Add products, capacity, facilities, collateral, management profiles, customer concentration, supplier concentration, risks and mitigants.",
                "Keep revenue, EBITDA, net worth, debt and requested limits mathematically plausible.",
                "Amounts are INR lakh.",
                "Return one JSON object containing every required key.",
            ],
        }
        generated = self.generate_json(prompt, fallback)
        # Keep the deterministic core fields and their types stable because the
        # PDF/table builders consume them directly. AI output may add richer
        # context keys, but cannot replace identifiers, numbers, or string lists.
        merged = {**generated, **fallback}
        merged["_generated_document_summaries"] = []
        return merged

    def generate_document(
        self,
        filename: str,
        context: dict[str, object],
    ) -> dict[str, object]:
        fallback = {
            "title": filename.removesuffix(".pdf").replace("_", " "),
            "document_summary": document_summary(filename, context),
            "sections": [
                {
                    "heading": heading,
                    "paragraphs": paragraphs,
                    "table": table,
                }
                for heading, paragraphs, table in document_sections(
                    filename,
                    context,
                )
            ],
        }
        compact_context = {
            key: value
            for key, value in context.items()
            if key != "_generated_document_summaries"
        }
        prompt = {
            "task": f"Create a detailed synthetic credit document for {filename}.",
            "borrowerContext": compact_context,
            "previousDocuments": context.get(
                "_generated_document_summaries",
                [],
            ),
            "requiredShape": {
                "title": "Human-readable title",
                "document_summary": "Detailed credit-focused summary",
                "sections": [
                    {
                        "heading": "Specific heading",
                        "paragraphs": ["Detailed paragraph"],
                        "table": [["Header", "Header"], ["Value", "Value"]],
                    }
                ],
            },
            "rules": [
                "Create 5 to 8 substantive sections specific to this document type.",
                "Each section must contain credit-relevant detail, not generic filler.",
                "Include at least three useful tables where appropriate.",
                "Keep each table to at most 7 columns and every table cell under 80 words.",
                "Put long explanations in paragraphs instead of table cells.",
                "Reconcile identifiers, counterparties and financial values with borrowerContext.",
                "Use previousDocuments to prevent contradictions.",
                "Clearly state that the document contains synthetic testing data.",
            ],
        }
        generated = self.generate_json(prompt, fallback)
        sections = generated.get("sections")
        if not isinstance(sections, list) or len(sections) < 5:
            generated = fallback
        summaries = context.setdefault("_generated_document_summaries", [])
        if isinstance(summaries, list):
            summaries.append(
                {
                    "filename": filename,
                    "summary": str(
                        generated.get("document_summary")
                        or fallback["document_summary"]
                    )[:1000],
                }
            )
            if len(summaries) > 10:
                del summaries[:-10]
        return generated

    def generate_financial_rows(
        self,
        table_name: str,
        context: dict[str, object],
        fallback_rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        columns = TABLE_COLUMNS[table_name]
        prompt = {
            "task": f"Create detailed synthetic rows for {table_name}.",
            "borrowerContext": {
                key: value
                for key, value in context.items()
                if key != "_generated_document_summaries"
            },
            "columns": list(columns),
            "fallbackRows": fallback_rows,
            "requiredShape": {"rows": [{column: "value" for column in columns}]},
            "rules": [
                f"Return at least {len(fallback_rows)} rows.",
                "Every row must contain all listed columns.",
                "Preserve accounting logic and three-year trend consistency.",
                "Use INR lakh for financial values.",
                "Provide specific commentary and assumptions.",
                "Return a JSON object with key rows only.",
            ],
        }
        result = self.generate_json(
            prompt,
            {"rows": fallback_rows},
        )
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) < len(fallback_rows):
            return fallback_rows
        cleaned: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized = {column: row.get(column) for column in columns}
            if normalized.get(columns[0]) not in (None, ""):
                cleaned.append(normalized)
        return cleaned if len(cleaned) >= len(fallback_rows) else fallback_rows
