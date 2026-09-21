from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode

from .config import MISTRAL_POLICY_MODEL
from .database import db_connection


if trace.get_tracer_provider().__class__.__name__ == "ProxyTracerProvider":
    trace.set_tracer_provider(TracerProvider(resource=Resource.create({"service.name": "credit-policy-intelligence"})))

tracer = trace.get_tracer("credit-policy-intelligence.ai", "1.0.0")


def _usage(response) -> tuple[int | None, int | None, int | None]:
    """Extract provider token usage without estimating missing values."""
    try:
        value = response.model_dump(mode="json")
    except Exception:
        value = getattr(response, "__dict__", {})
    candidates = []

    def visit(item):
        if isinstance(item, dict):
            if any(key in item for key in ("prompt_tokens", "input_tokens", "completion_tokens", "output_tokens", "total_tokens")):
                candidates.append(item)
            for child in item.values():
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    if not candidates:
        return None, None, None
    usage = candidates[-1]
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


@contextmanager
def observe_ai(feature: str, operation: str, user_id: str, target: str | None = None, model: str = MISTRAL_POLICY_MODEL):
    """Create an OpenTelemetry span and persist its measured AI request metrics."""
    started_at = datetime.now(timezone.utc)
    started = perf_counter()
    response_holder = {"response": None}
    error = None
    with tracer.start_as_current_span(f"ai.{operation}") as span:
        span.set_attribute("gen_ai.system", "mistral_ai")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("cpi.ai.feature", feature)
        span.set_attribute("cpi.ai.operation", operation)
        if target:
            span.set_attribute("cpi.ai.target", target)
        try:
            yield response_holder
            span.set_status(Status(StatusCode.OK))
        except BaseException as caught:
            error = caught
            span.record_exception(caught)
            span.set_status(Status(StatusCode.ERROR, str(caught)))
            raise
        finally:
            ended_at = datetime.now(timezone.utc)
            latency_ms = round((perf_counter() - started) * 1000, 3)
            input_tokens, output_tokens, total_tokens = _usage(response_holder["response"])
            for name, value in (("gen_ai.usage.input_tokens", input_tokens), ("gen_ai.usage.output_tokens", output_tokens)):
                if value is not None:
                    span.set_attribute(name, value)
            context = span.get_span_context()
            try:
                with db_connection() as connection:
                    connection.execute("""
                        INSERT INTO ai_observability_spans
                          (span_id, trace_id, feature, operation, model, target, status, latency_ms,
                           input_tokens, output_tokens, total_tokens, error_type, error_message,
                           started_at, ended_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (format(context.span_id, "016x"), format(context.trace_id, "032x"), feature,
                          operation, model, target, "failed" if error else "success", latency_ms,
                          input_tokens, output_tokens, total_tokens,
                          type(error).__name__ if error else None, str(error)[:2000] if error else None,
                          started_at, ended_at))
            except Exception as persistence_error:
                span.record_exception(persistence_error)
