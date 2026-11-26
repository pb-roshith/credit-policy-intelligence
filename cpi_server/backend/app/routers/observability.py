from fastapi import APIRouter, Depends, Request

from ..database import db_connection
from ..data_encryption import decrypt_text
from ..security import audit_export, current_user

router = APIRouter()

LIVE_AI_TRIGGERS = (
    ('Executive Dashboard', 'portfolio_insights', 'Portfolio Insights'),
    ('Policy Intelligence', 'semantic_policy_copilot', 'Policy Copilot'),
    ('Compliance Review', 'compliance_copilot', 'Compliance Copilot'),
    ('Exception Management', 'exception_rationale', 'AI Exception Rationale'),
    ('Decision Simulator', 'scenario_recommendations', 'Scenario Recommendations'),
    ('Portfolio Analytics', 'portfolio_copilot', 'Portfolio Analytics Copilot'),
    ('Risk Knowledge', 'semantic_policy_extraction', 'Semantic Rule Extraction'),
    ('Risk Knowledge', 'semantic_policy_scope', 'Policy Scope Extraction'),
    ('Compliance Review', 'graph_rag_explanation', 'Graph Evidence Explanation'),
)

LIVE_SPANS = """
    WITH catalog AS (
        SELECT * FROM unnest(%s::text[], %s::text[], %s::text[])
            AS triggers(feature, operation, display_name)
    ), live_spans AS (
        SELECT spans.* FROM "user".current_ai_observability_spans spans
        JOIN catalog USING (feature, operation)
    )
"""


@router.get("/api/observability")
def observability(_: dict = Depends(current_user)):
    return observability_snapshot(include_traces=True)


@router.post("/api/observability/export")
def export_observability(request: Request, user: dict = Depends(current_user)):
    report = observability_snapshot(include_traces=False)
    audit_export(request, user, "ai-telemetry-summary")
    return report


def observability_snapshot(*, include_traces: bool):
    """Aggregate account-scoped OpenTelemetry spans for user-facing AI features."""
    catalog_columns = tuple(map(list, zip(*LIVE_AI_TRIGGERS)))
    with db_connection() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        overview = dict(connection.execute(LIVE_SPANS + """
            SELECT COUNT(*) AS total_requests,
                   COUNT(*) FILTER (WHERE status = 'success') AS successful,
                   COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                   ROUND(AVG(latency_ms), 1) AS average_latency_ms,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM live_spans
        """, catalog_columns).fetchone())
        features = connection.execute(LIVE_SPANS + """
            , aggregate AS (
              SELECT feature, operation, COUNT(*) AS total_requests,
                     COUNT(*) FILTER (WHERE status='success') AS successful,
                     COUNT(*) FILTER (WHERE status='failed') AS failed,
                     ROUND(AVG(latency_ms), 1) AS average_latency_ms,
                     COALESCE(SUM(input_tokens), 0) AS input_tokens,
                     COALESCE(SUM(output_tokens), 0) AS output_tokens,
                     COALESCE(SUM(total_tokens), 0) AS total_tokens,
                     MAX(started_at) AS last_request_at
              FROM live_spans GROUP BY feature, operation
            )
            SELECT catalog.feature, catalog.operation, catalog.display_name,
                   COALESCE(aggregate.total_requests, 0) AS total_requests,
                   COALESCE(aggregate.successful, 0) AS successful,
                   COALESCE(aggregate.failed, 0) AS failed,
                   aggregate.average_latency_ms,
                   COALESCE(aggregate.input_tokens, 0) AS input_tokens,
                   COALESCE(aggregate.output_tokens, 0) AS output_tokens,
                   COALESCE(aggregate.total_tokens, 0) AS total_tokens,
                   aggregate.last_request_at
            FROM catalog LEFT JOIN aggregate USING (feature, operation)
            ORDER BY catalog.feature, catalog.operation
        """, catalog_columns).fetchall()
        traces = connection.execute(LIVE_SPANS + """
            SELECT span_id, trace_id, feature, operation, model, target, status,
                   latency_ms, input_tokens, output_tokens, total_tokens,
                   started_at, ended_at, input_payload, output_payload,
                   retrieved_sources, flow_steps
            FROM live_spans
            ORDER BY started_at DESC LIMIT 200
        """, catalog_columns).fetchall() if include_traces else []
        generated_at = connection.execute("SELECT CURRENT_TIMESTAMP AS value").fetchone()["value"]
    for trace in traces:
        trace["input_payload"] = decrypt_text(trace["input_payload"])
        trace["output_payload"] = decrypt_text(trace["output_payload"])
    return {"overview": overview, "features": features, "traces": traces, "generated_at": generated_at}
