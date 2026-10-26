"""Exercise creation, isolation and analyst approval; all writes are rolled back."""
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql
from app.database import shared_policy_connection
from app.security import current_user
from app.routers.exceptions import router


class ExceptionWorkflowDatabaseTests(unittest.TestCase):
    def test_managers_create_and_view_and_analyst_approves(self):
        connection = shared_policy_connection()
        try:
            managers = connection.execute('''SELECT DISTINCT ON (u.user_id) u.user_id, cr.credit_request_number
                FROM public.users u JOIN "user".credit_requests cr USING (user_id)
                WHERE u.role='relationship_manager' ORDER BY u.user_id, cr.credit_request_number LIMIT 2''').fetchall()
            self.assertEqual(len(managers), 2, 'Integration test requires two managers with local credit requests')
            user = {'user_id': managers[0]['user_id'], 'role': 'relationship_manager'}

            @contextmanager
            def scoped():
                connection.execute('RESET ROLE')
                connection.execute(sql.SQL('SET LOCAL app.user_id TO {}').format(sql.Literal(user['user_id'])))
                connection.execute('SET LOCAL ROLE credit_user_runtime')
                connection.execute('SET LOCAL search_path TO "user"')
                yield connection

            @contextmanager
            def shared():
                connection.execute('RESET ROLE')
                yield connection

            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[current_user] = lambda: user
            rationale = {key: 'Integration test rationale' for key in (
                'why_detected', 'business_justification', 'risk_implication',
                'recommended_remediation', 'escalation_required')}

            def persist(operation):
                with scoped() as db:
                    return operation(db)

            with TestClient(app) as client, \
                 patch('app.routers.exceptions.db_connection', scoped), \
                 patch('app.routers.exceptions.shared_policy_connection', shared), \
                 patch('app.routers.exceptions.run_db_transaction', persist), \
                 patch('app.routers.exceptions.generate_exception_rationale', return_value=rationale):
                created = []
                for manager in managers:
                    user['user_id'] = manager['user_id']
                    payload = {'credit_request_number': manager['credit_request_number'],
                        'exception_type': 'Integration test', 'clause_code': 'TEST-1', 'owner': user['user_id'],
                        'due_date': str(date.today() + timedelta(days=30)), 'status': 'Pending Approval',
                        'description': 'Temporary integration test exception.'}
                    response = client.post('/api/exceptions', json=payload)
                    self.assertEqual(response.status_code, 201, response.text)
                    created.append(response.json())
                    self.assertEqual(client.post('/api/exceptions/' + created[-1]['id'] + '/action', json={'action': 'approve'}).status_code, 403)
                deal_id = 'deal_' + 'a' * 24
                deal_context = {'credit_request_number': deal_id, 'borrower_name': 'Test Dossier Borrower',
                    'industry': 'Manufacturing', 'facility': 'Term Loan', 'rating': 'BBB',
                    'exposure': 1000, 'requested_amount': 1000, 'status': 'Pending'}
                with patch('app.routers.exceptions.deal_assessment_context', return_value=deal_context):
                    response = client.post('/api/exceptions', json={**payload, 'credit_request_number': deal_id})
                    self.assertEqual(response.status_code, 201, response.text)
                    self.assertEqual(response.json()['credit_request_number'], deal_id)
                    created.append(response.json())
                own = client.get('/api/exceptions').json()
                self.assertTrue(all(row['account_user_id'] == managers[1]['user_id'] for row in own))
                connection.execute('RESET ROLE')
                connection.execute("INSERT INTO public.users(user_id,password_hash,role,status,questions,created_at) VALUES ('integration-analyst','test','credit_analyst','approved','[]',now()) ON CONFLICT(user_id) DO UPDATE SET role='credit_analyst',status='approved',locked=false")
                user.update(user_id='integration-analyst', role='credit_analyst')
                registry = client.get('/api/exceptions').json()
                keys = {(row['account_user_id'], row['id']) for row in registry}
                for exception in created:
                    self.assertIn((exception['account_user_id'], exception['id']), keys)
                target = created[0]
                response = client.post('/api/exceptions/' + target['id'] + '/action', json={
                    'action': 'approve', 'account_user_id': target['account_user_id'], 'actor': 'forged'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['actor'], 'integration-analyst')
                self.assertEqual(response.json()['status'], 'Remediation')
                user.update(user_id=managers[0]['user_id'], role='relationship_manager')
                visible = client.get('/api/exceptions').json()
                self.assertEqual(next(row for row in visible if row['id'] == target['id'])['status'], 'Remediation')
        finally:
            connection.rollback()
            connection.close()
