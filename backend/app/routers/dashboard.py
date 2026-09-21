from fastapi import APIRouter, Depends

from ..database import db_connection
from ..schemas import PortfolioChatRequest
from ..security import current_user
from ..services.dashboard_agent import PortfolioInsightsAgent
from ..services.portfolio_agent import PortfolioChatAgent

router = APIRouter()


@router.get("/api/dashboard")
def dashboard(_: dict = Depends(current_user)):
    with db_connection() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        metrics = dict(connection.execute("""
            SELECT COUNT(*) FILTER (WHERE status IN ('In Review', 'Escalated', 'Pending')) AS active_requests,
                   ROUND(AVG(compliance_score), 1) AS policy_compliance
            FROM credit_requests
        """).fetchone())
        metrics.update(connection.execute("""
            SELECT COUNT(*) AS open_exceptions,
                   COUNT(*) FILTER (WHERE severity = 'High') AS high_severity,
                   COUNT(*) FILTER (WHERE due_date < CURRENT_DATE) AS overdue
            FROM credit_request_exceptions WHERE status <> 'Closed'
        """).fetchone())
        metrics['exception_exposure'] = connection.execute("""
            SELECT COALESCE(SUM(exposure), 0) AS total FROM credit_requests cr
            WHERE EXISTS (SELECT 1 FROM credit_request_exceptions e
                          WHERE e.credit_request_number = cr.credit_request_number AND e.status <> 'Closed')
        """).fetchone()['total']
        industries = connection.execute("""
            SELECT cr.industry AS label, COUNT(*) AS value
            FROM credit_request_exceptions e JOIN credit_requests cr USING (credit_request_number)
            WHERE e.status <> 'Closed' GROUP BY cr.industry ORDER BY value DESC, label
        """).fetchall()
        types = connection.execute("""
            SELECT exception_type AS label, SUM(exposure) AS value
            FROM credit_request_exceptions WHERE status <> 'Closed'
            GROUP BY exception_type ORDER BY value DESC, label
        """).fetchall()
        policies = connection.execute("""
            SELECT clause_code AS label, COUNT(*) AS value FROM credit_request_exceptions
            WHERE status <> 'Closed' GROUP BY clause_code ORDER BY value DESC, label LIMIT 5
        """).fetchall()
        trend = connection.execute(r"""
            WITH months AS (
                SELECT generate_series(date_trunc('month', CURRENT_DATE) - INTERVAL '5 months',
                                       date_trunc('month', CURRENT_DATE), INTERVAL '1 month') AS month
            ), closures AS (
                SELECT e.exception_id, MIN((event->>'date')::date) AS closed_on
                FROM credit_request_exceptions e CROSS JOIN LATERAL jsonb_array_elements(e.history) event
                WHERE event->>'event' IN ('Closed exception', 'Remediated exception')
                  AND event->>'date' ~ '^\d{4}-\d{2}-\d{2}$'
                GROUP BY e.exception_id
            )
            SELECT to_char(month, 'Mon YYYY') AS label,
                   (SELECT COUNT(*) FROM credit_request_exceptions e
                    WHERE e.created_at >= month AND e.created_at < month + INTERVAL '1 month') AS detected,
                   (SELECT COUNT(*) FROM closures c
                    WHERE c.closed_on >= month AND c.closed_on < month + INTERVAL '1 month') AS remediated
            FROM months ORDER BY month
        """).fetchall()
        payments = connection.execute("""
            SELECT payment_status AS label, SUM(outstanding_exposure) AS value
            FROM (
                SELECT DISTINCT ON (borrower_id, facility_reference)
                       payment_status, outstanding_exposure
                FROM borrower_exposure_history
                ORDER BY borrower_id, facility_reference, reporting_month DESC, exposure_record_id DESC
            ) latest GROUP BY payment_status ORDER BY label
        """).fetchall()
        generated_at = connection.execute("SELECT CURRENT_TIMESTAMP AS value").fetchone()['value']
        stored = connection.execute('''SELECT insights, generated_at, source_generated_at
            FROM dashboard_insights WHERE user_id = %s''', (_['user_id'],)).fetchone()
    return dict(metrics=metrics, industries=industries, types=types, policies=policies,
                trend=trend, payments=payments, insights=stored['insights'] if stored else [],
                insights_generated_at=stored['generated_at'] if stored else None,
                insights_source_generated_at=stored['source_generated_at'] if stored else None,
                generated_at=generated_at)


@router.post("/api/dashboard/insights")
def generate_insights(user: dict = Depends(current_user)):
    return PortfolioInsightsAgent().run(dashboard(user), user['user_id'])


@router.get("/api/portfolio")
def portfolio(_: dict = Depends(current_user)):
    """Return portfolio analytics calculated from the signed-in user's tables."""
    with db_connection() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        sectors = connection.execute("""
            WITH totals AS (
                SELECT COALESCE(SUM(exposure), 0) AS exposure FROM credit_requests
            ), breaches AS (
                SELECT credit_request_number, COUNT(*) AS count
                FROM credit_request_exceptions
                WHERE status <> 'Closed'
                GROUP BY credit_request_number
            )
            SELECT cr.industry AS label,
                   SUM(cr.exposure) AS exposure,
                   CASE WHEN totals.exposure = 0 THEN 0 ELSE
                       ROUND(SUM(cr.exposure) * 100.0 / totals.exposure, 1)
                   END AS exposure_percent,
                   COALESCE(SUM(b.count), 0) AS breaches
            FROM credit_requests cr
            CROSS JOIN totals
            LEFT JOIN breaches b USING (credit_request_number)
            GROUP BY cr.industry, totals.exposure
            ORDER BY exposure DESC, label
        """).fetchall()
        geographies = connection.execute("""
            WITH totals AS (
                SELECT COALESCE(SUM(exposure), 0) AS exposure FROM credit_requests
            ), breaches AS (
                SELECT credit_request_number, COUNT(*) AS count
                FROM credit_request_exceptions
                WHERE status <> 'Closed'
                GROUP BY credit_request_number
            )
            SELECT cr.geography AS label,
                   COALESCE(MAX(cc.geography_risk), 'Unknown') AS risk,
                   SUM(cr.exposure) AS exposure,
                   CASE WHEN totals.exposure = 0 THEN 0 ELSE
                       ROUND(SUM(cr.exposure) * 100.0 / totals.exposure, 1)
                   END AS exposure_percent,
                   COALESCE(SUM(b.count), 0) AS breaches
            FROM credit_requests cr
            CROSS JOIN totals
            LEFT JOIN credit_request_compliance cc USING (credit_request_number)
            LEFT JOIN breaches b USING (credit_request_number)
            GROUP BY cr.geography, totals.exposure
            ORDER BY exposure DESC, label
        """).fetchall()
        trend = connection.execute(r"""
            WITH months AS (
                SELECT generate_series(date_trunc('month', CURRENT_DATE) - INTERVAL '5 months',
                                       date_trunc('month', CURRENT_DATE), INTERVAL '1 month') AS month
            ), closures AS (
                SELECT e.exception_id, MIN((event->>'date')::date) AS closed_on
                FROM credit_request_exceptions e
                CROSS JOIN LATERAL jsonb_array_elements(e.history) event
                WHERE event->>'event' IN ('Closed exception', 'Remediated exception')
                  AND event->>'date' ~ '^\d{4}-\d{2}-\d{2}$'
                GROUP BY e.exception_id
            )
            SELECT to_char(month, 'Mon YYYY') AS label,
                   (SELECT COUNT(*) FROM credit_request_exceptions e
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
            FROM credit_request_exceptions WHERE status <> 'Closed'
            GROUP BY clause_code ORDER BY breaches DESC, label LIMIT 5
        """).fetchall()
        generated_at = connection.execute(
            "SELECT CURRENT_TIMESTAMP AS value"
        ).fetchone()['value']
    return dict(sectors=sectors, geographies=geographies, trend=trend, rwa=rwa,
                ecl=ecl, clauses=clauses, generated_at=generated_at)


@router.post("/api/portfolio/chat")
def portfolio_chat(payload: PortfolioChatRequest, user: dict = Depends(current_user)):
    snapshot = portfolio(user)
    history = [message.model_dump() for message in payload.history]
    return PortfolioChatAgent().run(snapshot, payload.question.strip(), history, user["user_id"])
