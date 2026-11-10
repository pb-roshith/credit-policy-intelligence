from contextlib import contextmanager
from functools import wraps
from datetime import datetime, timezone
import json
from time import perf_counter

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode

from .config import MISTRAL_POLICY_MODEL
from .database import run_db_transaction, account_user_id


if trace.get_tracer_provider().__class__.__name__ == "ProxyTracerProvider":
    trace.set_tracer_provider(TracerProvider(resource=Resource.create({"service.name": "credit-policy-intelligence"})))

tracer = trace.get_tracer("credit-policy-intelligence.ai", "1.0.0")


def record_ai_call(feature, operation, call, *, telemetry_target=None, telemetry_model=None, **arguments):
    """Record a provider request in the initiating account, including worker calls."""
    owner = account_user_id.get()
    # Offline scripts/tests without an account must not create account telemetry.
    if not owner:
        return call(**arguments)
    payload = arguments.get('messages', arguments.get('inputs'))
    if payload is None:
        payload = (arguments.get('json') or {}).get('messages', [])
    model = telemetry_model or arguments.get('model') or MISTRAL_POLICY_MODEL
    with observe_ai(feature, operation, owner, telemetry_target, model=model,
                    input_payload=json.dumps(payload, default=str),
                    retrieved_sources=['Supplied policy and request context']) as capture:
        response = call(**arguments)
        if hasattr(response, 'status_code') and isinstance(response.status_code, int) and response.status_code >= 400:
            raise ValueError(f'External provider returned HTTP {response.status_code}; response body omitted to protect credentials.')
        capture['response'] = response
        return response


def account_ai_job(function):
    """Restore the initiating account for background inventory jobs."""
    @wraps(function)
    def wrapped(job_id, user, *args, **kwargs):
        token = account_user_id.set(user['user_id'])
        try:
            return function(job_id, user, *args, **kwargs)
        finally:
            account_user_id.reset(token)
    return wrapped


def _usage(response) -> tuple[int | None, int | None, int | None]:
    """Extract provider token usage without estimating missing values."""
    try:
        value = response.model_dump(mode="json")
    except Exception:
        try:
            value = response.json()
        except Exception:
            value = getattr(response, "__dict__", {})
    candidates = []

    visited: set[int] = set()

    def visit(item, depth: int = 0):
        if depth > 20 or len(visited) >= 10_000:
            return
        identity = id(item)
        if identity in visited:
            return
        visited.add(identity)
        if isinstance(item, dict):
            if any(key in item for key in ("prompt_tokens", "input_tokens", "completion_tokens", "output_tokens", "total_tokens")):
                candidates.append(item)
            for child in item.values():
                visit(child, depth + 1)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child, depth + 1)

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


def _response_text(response) -> str | None:
    """Return a readable provider response without depending on one SDK shape."""
    if response is None:
        return None
    # Configurable OpenAI-compatible providers return an HTTP response.
    if hasattr(response, 'json'):
        try:
            payload = response.json()
            if isinstance(payload, dict):
                choices = payload.get('choices') or []
                if choices:
                    return choices[0].get('message', {}).get('content') or json.dumps(payload)
        except Exception:
            pass
    choices = getattr(response, "choices", None) or []
    if choices:
        content = getattr(getattr(choices[0], "message", None), "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
    for output in getattr(response, "outputs", []) or []:
        content = getattr(output, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = [str(getattr(item, "text", "")).strip() for item in content]
            value = "\n".join(part for part in parts if part)
            if value:
                return value
    try:
        return json.dumps(response.model_dump(mode="json"), default=str)
    except Exception:
        value = str(response).strip()
        return value or None


@contextmanager
def observe_ai(feature: str, operation: str, user_id: str, target: str | None = None,
               model: str = MISTRAL_POLICY_MODEL, input_payload: str | None = None,
               retrieved_sources: list[str] | None = None):
    """Create an OpenTelemetry span and persist its measured AI request metrics."""
    started_at = datetime.now(timezone.utc)
    started = perf_counter()
    response_holder = {
        "response": None,
        "input": input_payload,
        "sources": list(dict.fromkeys(retrieved_sources or [])),
    }
    error = None
    with tracer.start_as_current_span(f"ai.{operation}") as span:
        from .config import AI_PROVIDER
        span.set_attribute("gen_ai.system", "google_genai" if AI_PROVIDER == "gemini" else "mistral_ai")
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
            capture_started = perf_counter()
            input_tokens, output_tokens, total_tokens = _usage(response_holder["response"])
            output_payload = _response_text(response_holder["response"])
            capture_ms = round((perf_counter() - capture_started) * 1000, 3)
            sources = response_holder.get("sources") or []
            flow_steps = [
                {"name": "AI feature triggered", "duration_ms": 0, "status": "success",
                 "timestamp": started_at.isoformat(),
                 "description": f"User started {operation.replace('_', ' ')} in {feature}."},
                {"name": "Live sources retrieved", "duration_ms": None, "status": "success",
                 "timestamp": started_at.isoformat(), "source_count": len(sources), "sources": sources,
                 "description": f"{len(sources)} source{'s were' if len(sources) != 1 else ' was'} retrieved and grounded into the request."},
                {"name": "Request sent to AI provider", "duration_ms": None, "status": "success",
                 "timestamp": started_at.isoformat(), "model": model,
                 "input_characters": len(response_holder.get("input") or ""),
                 "description": f"The grounded prompt was sent to {model}."},
                {"name": "AI provider response received", "duration_ms": latency_ms,
                 "status": "failed" if error else "success",
                 "timestamp": ended_at.isoformat(), "output_characters": len(output_payload or ""),
                 "input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens,
                 "description": "The AI provider returned the model response; this duration is the measured end-to-end AI span." if not error else "The AI request failed before a usable response was returned."},
                {"name": "Response captured for audit", "duration_ms": capture_ms, "status": "success",
                 "timestamp": ended_at.isoformat(),
                 "description": "Output, usage, evidence, status, and timing were saved to this audit trace."},
            ]
            for name, value in (("gen_ai.usage.input_tokens", input_tokens), ("gen_ai.usage.output_tokens", output_tokens)):
                if value is not None:
                    span.set_attribute(name, value)
            context = span.get_span_context()
            try:
                def persist(connection):
                    connection.execute("""
                        INSERT INTO ai_observability_spans
                          (span_id, trace_id, feature, operation, model, target, status, latency_ms,
                           input_tokens, output_tokens, total_tokens, error_type, error_message,
                           started_at, ended_at, input_payload, output_payload,
                           retrieved_sources, flow_steps)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                    """, (format(context.span_id, "016x"), format(context.trace_id, "032x"), feature,
                          operation, model, target, "failed" if error else "success", latency_ms,
                          input_tokens, output_tokens, total_tokens,
                          type(error).__name__ if error else None, str(error)[:2000] if error else None,
                          started_at, ended_at, response_holder.get("input"), output_payload,
                          json.dumps(sources), json.dumps(flow_steps)))
                run_db_transaction(persist)
            except Exception as persistence_error:
                span.record_exception(persistence_error)
