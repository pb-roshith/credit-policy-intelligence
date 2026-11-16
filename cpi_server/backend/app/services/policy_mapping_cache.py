"""Persist current deterministic mappings; never reuse stale model decisions."""
import json
from datetime import date
from ..database import db_connection
from .assessment_request import normalize_request_id
from .semantic_matching import load_matcher
from .rule_assessment import assessment_request_context


def get_request_policy_mapping(request_number, user):
    request_id, data = assessment_request_context(normalize_request_id(request_number), user)
    report = load_matcher().match(data)
    with db_connection() as connection:
        stored = connection.execute('''INSERT INTO request_policy_mapping_cache(user_id,request_id,report)
            VALUES (%s,%s,%s::jsonb) ON CONFLICT(user_id,request_id)
            DO UPDATE SET report=EXCLUDED.report,generated_at=CURRENT_TIMESTAMP
            RETURNING generated_at''', (user['user_id'], request_id, json.dumps(report, default=str))).fetchone()
    return {**report, 'request_id': request_id, 'stored_at': stored['generated_at'], 'cached': False}
