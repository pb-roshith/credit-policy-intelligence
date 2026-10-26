"""Transactional integration checks for the analyst's combined manager portfolio."""
import os
import unittest
from contextlib import contextmanager, ExitStack
from unittest.mock import patch
from uuid import uuid4
from app.database import _connect
from app.schemas import GenerateCreditRequestsRequest, GenerateExceptionsRequest, GenerateBorrowerExposureRequest
from app.manufacture_data.credit_requests import generate_credit_requests, generate_exceptions
from app.manufacture_data.exposure_history import generate_borrower_exposure_history
from app.routers.requests import credit_requests
from app.services.dashboard_requests import request_totals


@unittest.skipUnless(os.getenv('RUN_ANALYST_DB_TESTS') == '1', 'Enable analyst PostgreSQL tests')
class AnalystVisibilityTests(unittest.TestCase):
    def test_twenty_plus_ten_requests_and_related_data(self):
        with ExitStack() as stack:
            c = _connect()
            stack.callback(c.close)
            stack.callback(c.rollback)
            prefix = 'visibility_' + uuid4().hex[:10]
            managers = [prefix + '_a', prefix + '_b']
            analyst = prefix + '_analyst'
            for owner, role in [(owner, 'relationship_manager') for owner in managers] + [(analyst, 'credit_analyst')]:
                c.execute("INSERT INTO public.users(user_id,password_hash,role,status,questions,created_at) VALUES (%s,'test',%s,'approved','[]',now())", (owner, role))
            @contextmanager
            def account():
                yield c
            for target in ('app.manufacture_data.credit_requests.db_connection', 'app.manufacture_data.exposure_history.db_connection', 'app.routers.requests.db_connection'):
                stack.enter_context(patch(target, account))
            stack.enter_context(patch('app.services.rule_assessment.active_rule_candidates', return_value=[]))
            def select(owner):
                c.execute('SET LOCAL ROLE NONE')
                c.execute("SELECT set_config('app.user_id',%s,true)", (owner,))
                c.execute('SET LOCAL ROLE credit_user_runtime')
                c.execute('SET LOCAL search_path TO "user"')
            for owner, count in zip(managers, (20, 10)):
                select(owner)
                c.execute("INSERT INTO approval_authority_rules(rule_order,maximum_post_approval_exposure,authority_name,authority_rank) VALUES (1,NULL,'Executive Committee',4)")
                actor = {'user_id': owner, 'role': 'relationship_manager'}
                generated = generate_credit_requests(GenerateCreditRequestsRequest(count=count), actor)
                generate_exceptions(GenerateExceptionsRequest(credit_request_numbers=[generated['credit_requests'][0]['credit_request_number']]), actor)
                generate_borrower_exposure_history(GenerateBorrowerExposureRequest(records_per_borrower=3), actor)
                rows = credit_requests(None, actor)
                self.assertEqual(len(rows), count)
                self.assertTrue(all(row['account_user_id'] == owner for row in rows))
            select(analyst)
            rows = credit_requests(None, {'user_id': analyst, 'role': 'credit_analyst'})
            fixture_rows = [row for row in rows if row['account_user_id'] in managers]
            self.assertEqual(len(fixture_rows), 30)
            self.assertEqual(len({row['credit_request_number'] for row in fixture_rows}), 30)
            self.assertEqual(request_totals([], fixture_rows, [])['total_requests'], 30)
            for table, expected in [('credit_request_compliance', 30), ('credit_data_records', 30), ('borrower_exposure_history', 90), ('credit_request_exceptions', 2)]:
                self.assertEqual(c.execute('SELECT count(*) AS n FROM ' + table + ' WHERE user_id=ANY(%s)', (managers,)).fetchone()['n'], expected)
            self.assertEqual(c.execute("UPDATE credit_requests SET status='Declined' WHERE user_id=ANY(%s)", (managers,)).rowcount, 0)
