"""Persist the first successful workbench policy mapping for each account/request."""
import json
from datetime import date

from ..database import db_connection
from .assessment_request import normalize_request_id
from .compliance_agent import latest_stored_compliance_review
from .policy_scope import policy_first_applicability
from .rule_assessment import assessment_request_context, active_rule_candidates


def _saved(connection, request_id, user_id):
    return connection.execute("""SELECT report, generated_at FROM request_policy_mapping_cache
        WHERE user_id = %s AND request_id = %s""", (user_id, request_id)).fetchone()


def _response(row, request_id, cached):
    return {**row['report'], 'request_id': request_id,
            'stored_at': row['generated_at'], 'cached': cached}


def get_request_policy_mapping(request_number, user):
    request_id = normalize_request_id(request_number)
    user_id = user['user_id']
    with db_connection() as connection:
        stored = _saved(connection, request_id, user_id)
    if stored:
        return _response(stored, request_id, True)

    # Validate access and obtain trusted request data before generating anything.
    request_id, data = assessment_request_context(request_id, user)
    with db_connection() as connection:
        # Serialize first-time generation across workers. Allow the connection to
        # remain idle while the model runs on its own connection.
        connection.execute("SET LOCAL idle_in_transaction_session_timeout = 0")
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                           (json.dumps(['request_policy_mapping', user_id, request_id]),))
        stored = _saved(connection, request_id, user_id)
        if stored:
            return _response(stored, request_id, True)
        review = latest_stored_compliance_review(request_id)
        if review and 'policy_mappings' in (review.get('applicability_report') or {}):
            report = {**review['applicability_report'], 'review_id': review['review_id']}
        else:
            report = policy_first_applicability(data, active_rule_candidates(date.today()), data.get('status'))
        stored = connection.execute("""INSERT INTO request_policy_mapping_cache (user_id, request_id, report)
            VALUES (%s, %s, %s::jsonb) RETURNING report, generated_at""",
            (user_id, request_id, json.dumps(report, default=str))).fetchone()
    return _response(stored, request_id, False)
