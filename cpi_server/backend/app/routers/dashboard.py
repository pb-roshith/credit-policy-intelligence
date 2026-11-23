from fastapi import APIRouter, Depends, HTTPException, Request

from ..database import db_connection, shared_policy_connection
from ..schemas import PortfolioChatRequest
from ..access_control import has_permission
from ..security import audit_export, current_user
from ..services.dashboard_agent import PortfolioInsightsAgent
from ..services.dashboard_chat import DashboardChatAgent
from ..services.portfolio_agent import PortfolioChatAgent
from ..services.shared_deals import call_shared_deals
from ..services.dashboard_requests import request_totals
from ..services.portfolio_concentration import concentrations
from ..services.current_knowledge import bind_current_views,current_reviews
from ..services.semantic_matching import load_matcher

router = APIRouter()


def portfolio_analyst(user: dict = Depends(current_user)):
    if not has_permission(user, "portfolio.access"):
        raise HTTPException(403, "Portfolio Analytics requires credit analyst access.")
    return user


def _top_violated_policies(counts, catalog):
    totals = {}
    for row in counts:
        code = row['clause_code']
        prefix, _, clause = code.partition('-')
        policy = next((p for p in catalog if p['policy_code'] == code
                       or p['library_policy_id'] == code), None)
        if policy is None:
            policy = next((p for p in catalog if clause and p['clause_number'] == clause
                           and (p['parent_policy'] or '').split('-')[0] == prefix), None)
        label = policy['title'] if policy else row['exception_type'] + ' Policy'
        totals[label] = totals.get(label, 0) + row['value']
    return [dict(label=label, value=value) for label, value in
            sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:5]]


@router.get("/api/dashboard")
def dashboard(_: dict = Depends(current_user)):
    knowledge=load_matcher()
    source_warning = None
    try:
        deals = call_shared_deals(_)
    except HTTPException:
        deals = []
        source_warning = "Credit Dossier deals could not be loaded. Totals currently include only account CPI requests."
    with db_connection() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        bind_current_views(connection,knowledge.fingerprint)
        metrics = dict(connection.execute("""
            SELECT COUNT(*) FILTER (WHERE status IN ('In Review', 'Escalated', 'Pending')) AS active_requests,
                   ROUND(AVG(compliance_score), 1) AS policy_compliance
            FROM credit_requests
        """).fetchone())
        metrics.update(connection.execute("""
            SELECT COUNT(*) AS open_exceptions,
                   COUNT(*) FILTER (WHERE severity = 'High') AS high_severity
            FROM current_policy_exceptions WHERE status <> 'Closed'
        """).fetchone())
        metrics['exception_exposure'] = connection.execute("""
            SELECT COALESCE(SUM(exposure), 0) AS total FROM (
                SELECT COALESCE(source_request_id, credit_request_number) AS request_id,
                       MAX(exposure) AS exposure
                FROM current_policy_exceptions WHERE status <> 'Closed'
                GROUP BY CASE WHEN COALESCE(source_request_id, credit_request_number) LIKE 'CR-%' THEN user_id ELSE NULL END, COALESCE(source_request_id, credit_request_number)
            ) affected_requests
        """).fetchone()['total']
        workflow_stages = connection.execute("""
            SELECT CASE status WHEN 'Active' THEN 'Reviewed'
                       WHEN 'Pending Approval' THEN 'Approved'
                       WHEN 'Remediation' THEN 'Remediated'
                       ELSE 'Detected' END AS label, COUNT(*) AS value
            FROM current_policy_exceptions WHERE status <> 'Closed'
            GROUP BY status ORDER BY label
        """).fetchall()
        types = connection.execute("""
            SELECT exception_type AS label, SUM(exposure) AS value
            FROM current_policy_exceptions WHERE status <> 'Closed'
            GROUP BY exception_type ORDER BY value DESC, label
        """).fetchall()
        policy_counts = connection.execute("""
            SELECT clause_code, exception_type, COUNT(*) AS value
            FROM current_policy_exceptions WHERE status <> 'Closed'
            GROUP BY clause_code, exception_type
        """).fetchall()
        trend = connection.execute(r"""
            WITH months AS (
                SELECT generate_series(date_trunc('month', CURRENT_DATE) - INTERVAL '5 months',
                                       date_trunc('month', CURRENT_DATE), INTERVAL '1 month') AS month
            ), closures AS (
                SELECT e.exception_id, MIN((event->>'date')::date) AS closed_on
                FROM current_policy_exceptions e CROSS JOIN LATERAL jsonb_array_elements(e.history) event
                WHERE event->>'event' IN ('Closed exception', 'Remediated exception')
                  AND event->>'date' ~ '^\d{4}-\d{2}-\d{2}$'
                GROUP BY e.user_id, e.exception_id
            )
            SELECT to_char(month, 'Mon YYYY') AS label,
                   (SELECT COUNT(*) FROM current_policy_exceptions e
                    WHERE e.created_at >= month AND e.created_at < month + INTERVAL '1 month') AS detected,
                   (SELECT COUNT(*) FROM closures c
                    WHERE c.closed_on >= month AND c.closed_on < month + INTERVAL '1 month') AS remediated
            FROM months ORDER BY month
        """).fetchall()
        payments = connection.execute("""
            SELECT payment_status AS label, SUM(outstanding_exposure) AS value
            FROM (
                SELECT DISTINCT ON (user_id, borrower_id, facility_reference)
                       payment_status, outstanding_exposure
                FROM borrower_exposure_history
                ORDER BY user_id, borrower_id, facility_reference, reporting_month DESC, exposure_record_id DESC
            ) latest GROUP BY payment_status ORDER BY label
        """).fetchall()
        generated_at = connection.execute("SELECT CURRENT_TIMESTAMP AS value").fetchone()['value']
        stored = connection.execute('''SELECT insights, generated_at, source_generated_at, knowledge_fingerprint
            FROM dashboard_insights WHERE user_id = %s''', (_['user_id'],)).fetchone()
        requests = connection.execute('''SELECT user_id AS account_user_id, credit_request_number, shared_deal_id,
            status, requested_amount, compliance_score FROM credit_requests''').fetchall()
        reviews = connection.execute('''SELECT DISTINCT ON (user_id, COALESCE(source_request_id, credit_request_number))
            user_id AS account_user_id, COALESCE(source_request_id, credit_request_number) AS request_id, review, created_at
            FROM ai_compliance_reviews
            ORDER BY user_id, COALESCE(source_request_id, credit_request_number), created_at DESC, review_id DESC''').fetchall()
    if stored and stored.get('knowledge_fingerprint')!=knowledge.fingerprint:stored=None
    reviews=current_reviews(reviews,knowledge.fingerprint)
    totals = request_totals(deals, requests, reviews)
    metrics.update({key: totals[key] for key in ('active_requests', 'total_requests',
        'assessed_requests', 'unassessed_requests', 'policy_compliance')})
    with shared_policy_connection() as connection:
        catalog = connection.execute("""
            SELECT policy_code, library_policy_id, clause_number, parent_policy, title
            FROM policy_documents ORDER BY display_order, policy_id
        """).fetchall()
    policies = _top_violated_policies(policy_counts, catalog)
    return dict(metrics=metrics, workflow_stages=workflow_stages, types=types, policies=policies,
                request_statuses=totals['request_statuses'], requested_amounts=totals['requested_amounts'],
                data_scope=("All relationship manager requests, compliance records, exceptions and exposure history, plus your own records."
                            if _['role'] == 'credit_analyst' else "Your Credit Dossier deals and CPI requests, compliance records, exceptions and exposure history."),
                source_warning=source_warning,
                trend=trend, payments=payments, insights=stored['insights'] if stored else [],
                insights_generated_at=stored['generated_at'] if stored else None,
                insights_source_generated_at=stored['source_generated_at'] if stored else None,
                generated_at=generated_at,knowledge_fingerprint=knowledge.fingerprint)


@router.post("/api/dashboard/export")
def export_dashboard(request: Request, user: dict = Depends(current_user)):
    snapshot = dashboard(user)
    fields = ("metrics", "workflow_stages", "types", "policies", "request_statuses",
              "requested_amounts", "trend", "payments", "data_scope", "generated_at")
    report = {field: snapshot[field] for field in fields}
    audit_export(request, user, "executive-dashboard")
    return report


@router.post("/api/dashboard/insights")
def generate_insights(user: dict = Depends(current_user)):
    return PortfolioInsightsAgent().run(dashboard(user), user['user_id'])


@router.post("/api/dashboard/chat")
def dashboard_chat(payload: PortfolioChatRequest, user: dict = Depends(current_user)):
    return DashboardChatAgent().run(dashboard(user), payload.question,
                                    [message.model_dump() for message in payload.history], user['user_id'])


@router.get("/api/portfolio")
def portfolio(_: dict = Depends(portfolio_analyst)):
    """Return authorized portfolio data, including Dossier deals in concentrations."""
    knowledge=load_matcher()
    source_warning = None
    try:
        deals = call_shared_deals(_)
    except HTTPException:
        deals = []
        source_warning = "Credit Dossier deals could not be loaded. Concentrations currently include only CPI requests."
    with db_connection() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        bind_current_views(connection,knowledge.fingerprint)
        requests = connection.execute("""
            SELECT cr.user_id AS account_user_id, cr.credit_request_number, cr.shared_deal_id,
                   cr.industry, cr.geography, cr.exposure, NULL::text AS geography_risk
            FROM credit_requests cr
        """).fetchall()
        exceptions = connection.execute("""
            SELECT user_id AS account_user_id,
                   COALESCE(source_request_id, credit_request_number) AS request_id, COUNT(*) AS count
            FROM current_policy_exceptions WHERE status <> 'Closed'
            GROUP BY user_id, COALESCE(source_request_id, credit_request_number)
        """).fetchall()
        trend = connection.execute(r"""
            WITH months AS (
                SELECT generate_series(date_trunc('month', CURRENT_DATE) - INTERVAL '5 months',
                                       date_trunc('month', CURRENT_DATE), INTERVAL '1 month') AS month
            ), closures AS (
                SELECT e.exception_id, MIN((event->>'date')::date) AS closed_on
                FROM current_policy_exceptions e
                CROSS JOIN LATERAL jsonb_array_elements(e.history) event
                WHERE event->>'event' IN ('Closed exception', 'Remediated exception')
                  AND event->>'date' ~ '^\d{4}-\d{2}-\d{2}$'
                GROUP BY e.user_id, e.exception_id
            )
            SELECT to_char(month, 'Mon YYYY') AS label,
                   (SELECT COUNT(*) FROM current_policy_exceptions e
                    WHERE e.created_at >= month AND e.created_at < month + INTERVAL '1 month') AS detected,
                   (SELECT COUNT(*) FROM closures c
                    WHERE c.closed_on >= month AND c.closed_on < month + INTERVAL '1 month') AS remediated
            FROM months ORDER BY month
        """).fetchall()
        rwa = connection.execute("""
            WITH weighted AS (
                SELECT industry,
                       exposure * CASE
                           WHEN rating IN ('AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-') THEN 0.50
                           WHEN rating IN ('BBB+', 'BBB', 'BBB-') THEN 0.75
                           WHEN rating IN ('BB+', 'BB', 'BB-') THEN 1.00
                           ELSE 1.50
                       END AS amount
                FROM credit_requests
            )
            SELECT industry AS label, ROUND(SUM(amount) / 1000000.0, 1) AS value
            FROM weighted GROUP BY industry ORDER BY value DESC, label
        """).fetchall()
        ecl = connection.execute("""
            WITH months AS (
                SELECT generate_series(date_trunc('month', CURRENT_DATE) - INTERVAL '5 months',
                                       date_trunc('month', CURRENT_DATE), INTERVAL '1 month')::date AS month
            ), monthly AS (
                SELECT date_trunc('month', reporting_month)::date AS month,
                       SUM(outstanding_exposure * CASE payment_status
                           WHEN 'Current' THEN 0.0045
                           WHEN 'Delayed' THEN 0.045
                           ELSE 0.45
                       END) / 1000000.0 AS value
                FROM borrower_exposure_history
                GROUP BY date_trunc('month', reporting_month)::date
            )
            SELECT to_char(months.month, 'Mon YYYY') AS label,
                   ROUND(COALESCE(monthly.value, 0), 2) AS value
            FROM months LEFT JOIN monthly USING (month)
            ORDER BY months.month
        """).fetchall()
        clauses = connection.execute("""
            SELECT clause_code AS label, COUNT(*) AS breaches
            FROM current_policy_exceptions WHERE status <> 'Closed'
            GROUP BY clause_code ORDER BY breaches DESC, label LIMIT 5
        """).fetchall()
        generated_at = connection.execute(
            "SELECT CURRENT_TIMESTAMP AS value"
        ).fetchone()['value']
    concentration = concentrations(deals, requests, exceptions)
    return dict(**concentration, source_warning=source_warning,
                concentration_basis="CPI request exposure and Dossier deal exposure; deal amount is used when exposure is unavailable. Percentages are calculated separately for each currency.",
                trend=trend, rwa=rwa, ecl=ecl, clauses=clauses, generated_at=generated_at,knowledge_fingerprint=knowledge.fingerprint)


@router.post("/api/portfolio/chat")
def portfolio_chat(payload: PortfolioChatRequest, user: dict = Depends(portfolio_analyst)):
    snapshot = portfolio(user)
    history = [message.model_dump() for message in payload.history]
    return PortfolioChatAgent().run(snapshot, payload.question.strip(), history, user["user_id"])
