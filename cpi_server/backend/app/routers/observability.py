from fastapi import APIRouter, Depends

from ..database import db_connection
from ..security import current_user

router = APIRouter()


@router.get("/api/observability")
def observability(_: dict = Depends(current_user)):
    """Aggregate account-scoped OpenTelemetry spans for user-facing AI features."""
    with db_connection() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        overview = dict(connection.execute("""
            SELECT COUNT(*) AS total_requests,
                   COUNT(*) FILTER (WHERE status = 'success') AS successful,
                   COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                   ROUND(AVG(latency_ms), 1) AS average_latency_ms,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM ai_observability_spans
        """).fetchone())
        features = connection.execute("""
            WITH catalog(feature, operation, display_name) AS (VALUES
              ('Executive Dashboard', 'portfolio_insights', 'Portfolio Insights'),
              ('Policy Intelligence', 'policy_copilot', 'Policy Copilot'),
              ('Compliance Review', 'compliance_agent', 'AI Compliance Agent'),
              ('Compliance Review', 'compliance_copilot', 'Compliance Copilot'),
              ('Exception Management', 'exception_rationale', 'AI Exception Rationale'),
              ('Decision Simulator', 'scenario_recommendations', 'Scenario Recommendations'),
              ('Portfolio Analytics', 'portfolio_copilot', 'Portfolio Analytics Copilot')
            ), aggregate AS (
              SELECT feature, operation, COUNT(*) AS total_requests,
                     COUNT(*) FILTER (WHERE status='success') AS successful,
                     COUNT(*) FILTER (WHERE status='failed') AS failed,
                     ROUND(AVG(latency_ms), 1) AS average_latency_ms,
                     COALESCE(SUM(input_tokens), 0) AS input_tokens,
                     COALESCE(SUM(output_tokens), 0) AS output_tokens,
                     COALESCE(SUM(total_tokens), 0) AS total_tokens,
                     MAX(started_at) AS last_request_at
              FROM ai_observability_spans GROUP BY feature, operation
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
        """).fetchall()
        traces = connection.execute("""
            SELECT span_id, trace_id, feature, operation, model, target, status,
                   latency_ms, input_tokens, output_tokens, total_tokens,
                   started_at, ended_at, input_payload, output_payload,
                   retrieved_sources, flow_steps
            FROM ai_observability_spans
            ORDER BY started_at DESC LIMIT 200
        """).fetchall()
        generated_at = connection.execute("SELECT CURRENT_TIMESTAMP AS value").fetchone()["value"]
    return {"overview": overview, "features": features, "traces": traces, "generated_at": generated_at}
