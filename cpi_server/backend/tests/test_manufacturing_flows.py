"""Run with RUN_MANUFACTURING_DB_TESTS=1; all sample records roll back."""
import os
import unittest
from contextlib import contextmanager, ExitStack
from unittest.mock import patch
from uuid import uuid4

from app.database import _connect
from app.manufacture_data.credit_requests import generate_credit_requests, generate_exceptions
from app.manufacture_data.exposure_history import generate_borrower_exposure_history
from app.schemas import GenerateCreditRequestsRequest, GenerateExceptionsRequest, GenerateBorrowerExposureRequest


@unittest.skipUnless(os.getenv('RUN_MANUFACTURING_DB_TESTS') == '1', 'Enable PostgreSQL integration tests')
class ManufacturingTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.connection = _connect()
        self.stack.callback(self.connection.close)
        self.stack.callback(self.connection.rollback)
        self.stack.enter_context(patch('app.services.rule_assessment.active_rule_candidates', return_value=[]))
        self.user = {'user_id': 'manufacturing_test_' + uuid4().hex[:12], 'role': 'relationship_manager'}
        c = self.connection
        c.execute("SELECT set_config('app.user_id', %s, true)", (self.user['user_id'],))
        c.execute('SET LOCAL ROLE credit_user_runtime')
        c.execute('SET LOCAL search_path TO "user"')
        c.execute("INSERT INTO approval_authority_rules(rule_order, maximum_post_approval_exposure, authority_name, authority_rank) VALUES (1,NULL,'Executive Committee',4)")

        @contextmanager
        def account():
            yield c
        for target in ('app.manufacture_data.credit_requests.db_connection',
                       'app.manufacture_data.exposure_history.db_connection',
                       'app.database.db_connection'):
            self.stack.enter_context(patch(target, account))

    def test_requests_history_and_exceptions(self):
        result = generate_credit_requests(GenerateCreditRequestsRequest(count=10), self.user)
        numbers = [row['credit_request_number'] for row in result['credit_requests']]
        self.assertEqual(len(set(numbers)), 10)
        c = self.connection
        self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM credit_data_records').fetchone()['n'], 10)
        self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM credit_request_compliance WHERE uploaded_required_documents=0 AND synthetic_assessment_data IS NOT NULL').fetchone()['n'], 10)
        for _ in range(2):
            history = generate_borrower_exposure_history(GenerateBorrowerExposureRequest(records_per_borrower=6), self.user)
            self.assertEqual(history['record_count'], 60)
        self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM borrower_exposure_history').fetchone()['n'], 60)
        result = generate_exceptions(GenerateExceptionsRequest(credit_request_numbers=numbers[:3]), self.user)
        self.assertEqual(result['count'], 3)
        self.assertEqual(c.execute("SELECT COUNT(*) AS n FROM credit_request_exceptions WHERE status='Active'").fetchone()['n'], 3)

    def test_request_and_supporting_data_share_transaction(self):
        from app.services.credit_data import store_record
        connections = []
        def save(record, **kwargs):
            connections.append(kwargs.get('connection'))
            return store_record(record, **kwargs)
        with patch('app.services.credit_data.store_record', side_effect=save):
            generate_credit_requests(GenerateCreditRequestsRequest(count=1), self.user)
        self.assertEqual(connections, [self.connection])

    def test_dashboard_counts_shared_exposure_once_and_workflow_stages(self):
        from app.routers.dashboard import dashboard
        result = generate_credit_requests(GenerateCreditRequestsRequest(count=1), self.user)
        number = result['credit_requests'][0]['credit_request_number']
        for _ in range(2):
            generate_exceptions(GenerateExceptionsRequest(credit_request_numbers=[number]), self.user)
        # A shared deal may have exceptions without a local request projection.
        self.connection.execute("UPDATE credit_request_exceptions SET credit_request_number=NULL, source_request_id='deal_fixture', exposure=75000000, status='Pending Approval'")
        connection = self.connection
        class SnapshotConnection:
            def execute(self, query, *args):
                # The test already owns a rollback-only transaction with fixture writes.
                if query.startswith('SET TRANSACTION'):
                    return None
                return connection.execute(query, *args)
        @contextmanager
        def snapshot_connection():
            yield SnapshotConnection()
        @contextmanager
        def catalog_connection():
            connection.execute('SET LOCAL ROLE NONE')
            connection.execute('SET LOCAL search_path TO credit_data')
            try:
                yield connection
            finally:
                connection.execute('SET LOCAL ROLE credit_user_runtime')
                connection.execute('SET LOCAL search_path TO "user"')
        with patch('app.routers.dashboard.db_connection', snapshot_connection), patch('app.routers.dashboard.shared_policy_connection', catalog_connection), patch('app.routers.dashboard.call_shared_deals', return_value=[]):
            snapshot = dashboard(self.user)
        self.assertEqual(snapshot['metrics']['exception_exposure'], 75000000)
        self.assertEqual(snapshot['metrics']['open_exceptions'], 2)
        self.assertEqual(snapshot['metrics']['assessed_requests'], 1)
        self.assertEqual(snapshot['metrics']['policy_compliance'], result['credit_requests'][0]['compliance_score'])
        self.assertEqual(snapshot['workflow_stages'], [{'label': 'Approved', 'value': 2}])
        self.assertNotIn('overdue', snapshot['metrics'])
