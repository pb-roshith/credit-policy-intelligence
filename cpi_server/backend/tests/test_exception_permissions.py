import unittest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.security import current_user
from app.routers.exceptions import router


class ExceptionPermissionTests(unittest.TestCase):
    def setUp(self):
        self.user = {"user_id": "manager", "role": "relationship_manager"}
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[current_user] = lambda: self.user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_manager_cannot_approve_or_change_another_account(self):
        with patch('app.routers.exceptions.db_connection') as connection:
            for payload in ({"action": "approve"}, {"action": "close", "account_user_id": "other"}):
                response = self.client.post('/api/exceptions/EX-1/action', json=payload)
                self.assertEqual(response.status_code, 403)
            connection.assert_not_called()

    def test_analyst_cannot_create_exception(self):
        self.user = {'user_id': 'analyst', 'role': 'credit_analyst'}
        with patch('app.routers.exceptions.db_connection') as connection, \
             patch('app.routers.exceptions.deal_assessment_context') as deal_context:
            for request_id in ('CR-1', 'deal_1'):
                response = self.client.post('/api/exceptions', json={
                    'credit_request_number': request_id, 'exception_type': 'Policy', 'clause_code': 'POL-1',
                    'owner': 'analyst', 'due_date': '2099-01-01', 'status': 'Pending Approval',
                    'description': 'A policy deviation for review.'})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()['detail'], 'Only relationship managers can create exceptions.')
            connection.assert_not_called()
            deal_context.assert_not_called()

    def test_creation_persists_once_when_ai_rationale_is_pending(self):
        from app.services.exception_rationale import pending_exception_rationale
        pending = pending_exception_rationale({'description': 'A policy deviation for review.'})
        with patch('app.routers.exceptions.db_connection') as factory, \
             patch('app.routers.exceptions.generate_exception_rationale', return_value=pending), \
             patch('app.routers.exceptions.latest_stored_compliance_review',return_value={'knowledge_fingerprint':'current','findings':[{'rule_id':'urn:rule:1','policy_id':1}]}), \
             patch('app.routers.exceptions.run_db_transaction') as transaction:
            connection = factory.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.side_effect = [
                {'credit_request_number': 'CR-1', 'exposure': 1000}, None,
            ]
            persisted = MagicMock()
            persisted.execute.return_value.fetchone.side_effect = [
                {'value': 9001}, {'id': 'EX-9001', 'status': 'Active', 'rationale': pending},
            ]
            transaction.side_effect = lambda operation: operation(persisted)
            response = self.client.post('/api/exceptions', json={
                'credit_request_number': 'CR-1', 'exception_type': 'Policy', 'clause_code': 'POL-1',
                'owner': 'manager', 'due_date': '2099-01-01', 'status': 'Active',
                'description': 'A policy deviation for review.', 'semantic_rule_id':'urn:rule:1',
            })
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()['rationale']['generation_status'], 'pending')
            self.assertEqual(response.json()['status'], 'Active')
            transaction.assert_called_once()
            inserts = [call for call in persisted.execute.call_args_list if 'INSERT INTO' in call.args[0]]
            self.assertEqual(len(inserts), 1)
            self.assertIn('"generation_status": "pending"', inserts[0].args[1][-3])

    def test_creation_cannot_bypass_approval(self):
        with patch('app.routers.exceptions.db_connection') as connection:
            for status in ('Remediation', 'Closed'):
                response = self.client.post('/api/exceptions', json={
                    'credit_request_number': 'CR-1', 'exception_type': 'Policy', 'clause_code': 'POL-1',
                    'owner': 'manager', 'due_date': '2099-01-01', 'status': status,
                    'description': 'A policy deviation for review.'})
                self.assertEqual(response.status_code, 403)
            connection.assert_not_called()

    def test_analyst_approval_targets_account_and_uses_authenticated_actor(self):
        self.user = {'user_id': 'analyst', 'role': 'credit_analyst'}
        with patch('app.routers.exceptions.shared_policy_connection') as factory:
            connection = factory.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = {'status': 'Pending Approval', 'history': []}
            response = self.client.post('/api/exceptions/EX-1/action', json={
                'action': 'approve', 'account_user_id': 'manager', 'actor': 'forged'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['actor'], 'analyst')
            self.assertEqual(response.json()['status'], 'Remediation')
            self.assertEqual(connection.execute.call_args.args[1][-2:], ('manager', 'EX-1'))

    def test_registry_uses_database_row_permissions_for_both_roles(self):
        with patch('app.routers.exceptions.shared_policy_connection') as shared, \
             patch('app.routers.exceptions.db_connection') as scoped:
            scoped.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = []
            shared.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = []
            self.assertEqual(self.client.get('/api/exceptions').status_code, 200)
            shared.assert_not_called()
            self.user['role'] = 'credit_analyst'
            self.assertEqual(self.client.get('/api/exceptions').status_code, 200)
            shared.assert_not_called()
            self.assertEqual(scoped.call_count, 2)

    def test_manager_can_delete_own_exception_with_account_scope(self):
        with patch('app.routers.exceptions.db_connection') as factory:
            connection = factory.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = {'exception_id': 'EX-1'}
            response = self.client.delete('/api/exceptions/EX-1')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['deleted'])
            self.assertEqual(connection.execute.call_args.args[1], ('manager', 'EX-1'))
            self.assertIn('DELETE FROM', connection.execute.call_args.args[0])

    def test_manager_cannot_delete_another_account_exception(self):
        with patch('app.routers.exceptions.db_connection') as scoped, \
             patch('app.routers.exceptions.shared_policy_connection') as shared:
            response = self.client.request('DELETE', '/api/exceptions/EX-1', json={'user_id': 'other'})
            self.assertEqual(response.status_code, 403)
            scoped.assert_not_called()
            shared.assert_not_called()

    def test_analyst_can_delete_selected_account_exception(self):
        self.user = {'user_id': 'analyst', 'role': 'credit_analyst'}
        with patch('app.routers.exceptions.shared_policy_connection') as factory:
            connection = factory.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = {'exception_id': 'EX-1'}
            response = self.client.request('DELETE', '/api/exceptions/EX-1', json={'user_id': 'manager'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(connection.execute.call_args.args[1], ('manager', 'EX-1'))

    def test_delete_missing_exception_returns_not_found(self):
        with patch('app.routers.exceptions.db_connection') as factory:
            factory.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            self.assertEqual(self.client.delete('/api/exceptions/EX-1').status_code, 404)

    def test_other_roles_cannot_delete_exceptions(self):
        self.user['role'] = 'admin'
        with patch('app.routers.exceptions.db_connection') as scoped, \
             patch('app.routers.exceptions.shared_policy_connection') as shared:
            self.assertEqual(self.client.delete('/api/exceptions/EX-1').status_code, 403)
            scoped.assert_not_called()
            shared.assert_not_called()
