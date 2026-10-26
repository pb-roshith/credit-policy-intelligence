"""
Telemetry Module — centralized Mistral observability + local trace logging.

Provides:
- configure_telemetry() on the shared Mistral client (redaction=True, provider="dedicated")
- get_telemetry_tracer() for manual span instrumentation across services
- Custom span attributes (credit_dossier.*) for filtering on the Mistral dashboard

Mistral SDK API (v2.7+):
- configure_telemetry(client, provider="dedicated", redaction=True)
- get_telemetry_tracer(client, "service-name") → OpenTelemetry Tracer
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mistralai.client import Mistral

logger = logging.getLogger(__name__)

# ── Module State ─────────────────────────────────────────────────────
_telemetry_configured = False
_tracer = None


def setup_telemetry(client: "Mistral") -> None:
    """
    Configure Mistral's built-in telemetry on the given client.

    Called once when the Mistral client is first created.
    Uses redaction=True to protect sensitive financial data in traces.
    Sends traces to Mistral's dedicated telemetry backend.
    """
    global _telemetry_configured, _tracer

    if _telemetry_configured:
        return

    try:
        from mistralai.extra.observability import configure_telemetry, get_telemetry_tracer

        # Configure with redaction=True for production safety (financial data)
        configure_telemetry(client, provider="dedicated", redaction=True)

        # Get the tracer for manual span instrumentation
        _tracer = get_telemetry_tracer(client, "credit-dossier-api")

        _telemetry_configured = True
        logger.info(
            "✓ Mistral telemetry configured (provider=dedicated, redaction=True, "
            "tracer=credit-dossier-api)"
        )

    except ImportError as e:
        logger.warning(
            f"Mistral observability extras not available: {e}. "
            f"Install with: pip install 'mistralai[telemetry]'"
        )
    except Exception as e:
        logger.error(f"Failed to configure Mistral telemetry: {e}", exc_info=True)


def get_tracer():
    """
    Return the OpenTelemetry tracer for manual span creation.

    Usage:
        tracer = get_tracer()
        if tracer:
            with tracer.start_as_current_span("my_operation") as span:
                span.set_attribute("credit_dossier.section_key", "executive_summary")
                ...

    Returns None if telemetry is not configured.
    """
    return _tracer


@contextmanager
def trace_span(name: str, **attributes):
    """
    Convenience context manager for creating traced spans with custom attributes.

    Automatically handles the case where telemetry is not configured.

    Usage:
        with trace_span("generate_section", section_key="exec_summary", deal_id="123"):
            # ... do work ...

    Args:
        name: The span name
        **attributes: Custom attributes to set (auto-prefixed with credit_dossier.)
    """
    tracer = get_tracer()
    if tracer:
        with tracer.start_as_current_span(name) as span:
            for key, value in attributes.items():
                span.set_attribute(f"credit_dossier.{key}", str(value))
            yield span
    else:
        yield None


def is_telemetry_enabled() -> bool:
    """Check if telemetry has been successfully configured."""
    return _telemetry_configured


def extract_usage_metrics(response) -> dict[str, int]:
    """Extract token usage across Mistral chat, agent, and conversation responses."""
    usage = getattr(response, "usage", None) or getattr(response, "usage_info", None)
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def value(*names: str) -> int:
        for name in names:
            raw = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            if raw is not None:
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    continue
        return 0

    input_tokens = value("prompt_tokens", "input_tokens")
    output_tokens = value("completion_tokens", "output_tokens")
    total_tokens = value("total_tokens") or input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def estimate_text_tokens(text: str) -> int:
    """Estimate tokens for APIs, such as moderation, that omit usage metadata."""
    if not text:
        return 0
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


# ── Custom Attribute Helpers ─────────────────────────────────────────
# These helpers ensure consistent attribute naming across all services.
# All custom attributes use the "credit_dossier." prefix for Mistral dashboard filtering.


def set_span_attributes(span, **kwargs) -> None:
    """
    Set custom span attributes with the `credit_dossier.` prefix.

    Provides consistent naming for filtering on the Mistral dashboard.

    Args:
        span: The OpenTelemetry span to annotate
        **kwargs: Key-value pairs to set as attributes.
                  Keys are automatically prefixed with "credit_dossier."

    Example:
        set_span_attributes(span,
            deal_id="deal-123",
            section_key="executive_summary",
            operation="generate",
        )
        # Sets:
        #   credit_dossier.deal_id = "deal-123"
        #   credit_dossier.section_key = "executive_summary"
        #   credit_dossier.operation = "generate"
    """
    if span is None:
        return
    for key, value in kwargs.items():
        span.set_attribute(f"credit_dossier.{key}", str(value))


def set_gen_ai_attributes(span, **kwargs) -> None:
    """
    Set standard gen_ai.* attributes on a span (OpenTelemetry semantic conventions).

    Args:
        span: The OpenTelemetry span
        **kwargs: Key-value pairs (keys use gen_ai.* naming)
    """
    if span is None:
        return
    for key, value in kwargs.items():
        span.set_attribute(f"gen_ai.{key}", str(value))
