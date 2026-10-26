"""
Moderation Service — content guardrailing via Mistral's classifiers.moderate API.

Uses the `mistral-moderation-latest` model to check user-provided inputs
(custom instructions, output templates) before allowing narrative generation.

Categories checked:
  - sexual, hate_and_discrimination, violence_and_threats,
    dangerous_and_criminal_content, selfharm, health, financial, pii
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.telemetry import (
    extract_usage_metrics,
    estimate_text_tokens,
    get_tracer,
    set_gen_ai_attributes,
    set_span_attributes,
)

logger = logging.getLogger(__name__)

# Use shared Mistral client from mistral_library_service (has telemetry configured)
def _get_client():
    from app.services.mistral_library_service import _get_client as _get_shared_client
    return _get_shared_client()


# Model to use for moderation
MODERATION_MODEL = "mistral-moderation-latest"


@dataclass
class ModerationResult:
    """Result of a moderation check."""
    is_safe: bool
    flagged_categories: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_safe": self.is_safe,
            "flagged_categories": self.flagged_categories,
            "details": self.details,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


class ModerationService:
    """Provides content moderation using Mistral's classifiers API."""

    @staticmethod
    async def moderate_text(text: str) -> ModerationResult:
        """
        Moderate a single text string using Mistral's moderation classifier.

        Returns a ModerationResult with flagged categories and per-category details.
        """
        if not text or not text.strip():
            return ModerationResult(is_safe=True)

        client = _get_client()
        tracer = get_tracer()
        started_at = time.perf_counter()

        # Start telemetry span
        span_ctx = None
        span = None
        if tracer:
            span_ctx = tracer.start_as_current_span("moderation_check")
            span = span_ctx.__enter__()
            set_span_attributes(span,
                operation="moderation_check",
                content_length=str(len(text)),
            )
            set_gen_ai_attributes(span,
                system="mistral",
                request_model=MODERATION_MODEL,
            )

        try:
            response = await client.classifiers.moderate_async(
                model=MODERATION_MODEL,
                inputs=[text],
            )
            usage = extract_usage_metrics(response)
            if usage["input_tokens"] == 0:
                usage["input_tokens"] = estimate_text_tokens(text)
            if usage["total_tokens"] == 0:
                usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
            latency_ms = (time.perf_counter() - started_at) * 1000

            # response.results is a list (one per input)
            if not response.results:
                logger.warning("Moderation API returned empty results")
                return ModerationResult(is_safe=True)

            result = response.results[0]

            # Extract category results
            flagged_categories = []
            details = {}

            # The result has a `categories` dict with category name → flagged (bool)
            categories = getattr(result, "categories", {})
            category_scores = getattr(result, "category_scores", {})

            if isinstance(categories, dict):
                for category, flagged in categories.items():
                    details[category] = {
                        "flagged": flagged,
                        "score": category_scores.get(category, 0.0)
                            if isinstance(category_scores, dict) else 0.0,
                    }
                    if flagged:
                        flagged_categories.append(category)
            else:
                # Handle object-style attributes (Pydantic model)
                for attr_name in dir(categories):
                    if attr_name.startswith("_"):
                        continue
                    val = getattr(categories, attr_name, None)
                    if isinstance(val, bool):
                        score = 0.0
                        if category_scores:
                            score = getattr(category_scores, attr_name, 0.0)
                        details[attr_name] = {
                            "flagged": val,
                            "score": score,
                        }
                        if val:
                            flagged_categories.append(attr_name)

            is_safe = len(flagged_categories) == 0

            if not is_safe:
                logger.warning(
                    f"Content flagged by moderation: {flagged_categories}"
                )
            else:
                logger.info("Content passed moderation check")

            # Record moderation result in span
            if span:
                set_span_attributes(span,
                    result="flagged" if not is_safe else "safe",
                    flagged_categories=", ".join(flagged_categories) if flagged_categories else "none",
                )
            if span_ctx:
                span_ctx.__exit__(None, None, None)

            return ModerationResult(
                is_safe=is_safe,
                flagged_categories=flagged_categories,
                details=details,
                latency_ms=latency_ms,
                **usage,
            )

        except Exception as e:
            logger.error(f"Moderation API call failed: {e}")
            if span:
                set_span_attributes(span, result="error", error=str(e))
            if span_ctx:
                span_ctx.__exit__(type(e), e, e.__traceback__)
            # On API failure, default to safe to avoid blocking
            # (fail-open policy — can be changed to fail-closed)
            return ModerationResult(
                is_safe=True,
                details={"error": "Content moderation was temporarily unavailable."},
                latency_ms=(time.perf_counter() - started_at) * 1000,
            )

    @staticmethod
    async def moderate_section_inputs(
        custom_instructions: str | None = None,
        output_template: str | None = None,
    ) -> ModerationResult:
        """
        Moderate all user-provided inputs for a section.

        Checks custom_instructions and output_template separately,
        then combines results. If any input is flagged, the overall
        result is flagged.
        """
        all_flagged: list[str] = []
        all_details: dict[str, Any] = {}
        latency_ms = 0.0
        input_tokens = output_tokens = total_tokens = 0

        # Check custom instructions
        if custom_instructions and custom_instructions.strip():
            result = await ModerationService.moderate_text(custom_instructions)
            latency_ms += result.latency_ms
            input_tokens += result.input_tokens
            output_tokens += result.output_tokens
            total_tokens += result.total_tokens
            if not result.is_safe:
                all_flagged.extend(result.flagged_categories)
            all_details["custom_instructions"] = {
                "is_safe": result.is_safe,
                "flagged_categories": result.flagged_categories,
                "details": result.details,
            }

        # Check output template
        if output_template and output_template.strip():
            result = await ModerationService.moderate_text(output_template)
            latency_ms += result.latency_ms
            input_tokens += result.input_tokens
            output_tokens += result.output_tokens
            total_tokens += result.total_tokens
            if not result.is_safe:
                # Avoid duplicate categories
                for cat in result.flagged_categories:
                    if cat not in all_flagged:
                        all_flagged.append(cat)
            all_details["output_template"] = {
                "is_safe": result.is_safe,
                "flagged_categories": result.flagged_categories,
                "details": result.details,
            }

        is_safe = len(all_flagged) == 0

        return ModerationResult(
            is_safe=is_safe,
            flagged_categories=all_flagged,
            details=all_details,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
