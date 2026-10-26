"""CPI routes delegate to the shared account authority without local credentials."""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.routers.auth import router
from app.security import current_admin, resolve_session


class SharedIdentityProxyTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[current_admin] = lambda: {'user_id':'test-admin','role':'admin'}
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.answers = [{'question':q,'answer':'example answer'} for q in ('First question?', 'Second question?', 'Third question?')]

    def test_registration_uses_shared_namespace_and_stores_pending_mirror(self):
        with patch('app.routers.auth.db_connection') as factory, patch('app.services.dossier_identity.identity_call') as shared, patch('app.services.dossier_identity.mirror_identity') as mirror, patch('app.routers.auth.write_user_log'):
            factory.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            shared.return_value = {'user_id':'test-manager','role':'relationship_manager'}
            response = self.client.post('/api/auth/register', json={'user_id':'Test-Manager','password':'SyntheticOnly!123456','role':'relationship_manager','security_answers':self.answers})
            self.assertEqual(response.status_code,201,response.text)
            self.assertEqual(shared.call_args.args[2],'register')
            self.assertEqual(shared.call_args.args[1]['security_questions'],self.answers)
            self.assertEqual(shared.call_args.args[0],'test-manager')
            mirror.assert_called_once_with(shared.return_value,approved=False)

    def test_existing_name_never_creates_an_independent_account(self):
        with patch('app.routers.auth.db_connection') as factory, patch('app.services.dossier_identity.identity_call') as shared:
            factory.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {'value':1}
            result = self.client.post('/api/auth/register',json={'user_id':'duplicate','password':'SyntheticOnly!123456','role':'relationship_manager','security_answers':self.answers})
            self.assertEqual(result.status_code,409)
            shared.assert_not_called()

    def test_both_recovery_and_reset_use_shared_security_answers(self):
        with patch('app.services.dossier_identity.identity_call') as shared, patch('app.routers.auth.db_connection'), patch('app.routers.auth.revoke_user_sessions') as revoke, patch('app.routers.auth.write_user_log'):
            shared.return_value = {'questions':[a['question'] for a in self.answers]}
            self.assertEqual(self.client.get('/api/auth/recovery/test-manager').status_code,200)
            self.assertEqual(shared.call_args.args[2],'questions')
            shared.return_value = {'message':'Password reset successfully'}
            response = self.client.post('/api/auth/reset-password',json={'user_id':'test-manager','password':'ChangedOnly!123456','security_answers':self.answers})
            self.assertEqual(response.status_code,200)
            self.assertEqual(shared.call_args.args[2],'reset-password')
            self.assertEqual(shared.call_args.args[1]['new_password'],'ChangedOnly!123456')
            revoke.assert_called_once_with('test-manager')

    def test_shared_password_change_invalidates_existing_cpi_session(self):
        now = datetime.now(timezone.utc)
        row = {'user_id':'test-manager','role':'relationship_manager','auth_provider':'dossier','status':'approved','locked':False,'failed_attempts':0,'created_at':now,'dossier_user_id':'test-manager','dossier_credential_version':1}
        request = MagicMock(method='GET', cookies={'cpi_session':'test-session'})
        with patch('app.security.db_connection') as factory, patch('app.services.shared_deals.call_shared_deals',return_value={'user_id':'test-manager','role':'relationship_manager','credential_version':2}), patch('app.security.revoke_session') as revoke:
            factory.return_value.__enter__.return_value.execute.return_value.fetchone.side_effect = [{'user_id':'test-manager','role':'relationship_manager','expires_at':now+timedelta(minutes=10)}, row]
            with self.assertRaises(HTTPException) as error:
                resolve_session(request)
            self.assertEqual(error.exception.status_code,401)
            revoke.assert_called_once_with('test-session')

    def test_admin_user_list_still_serializes_shared_identities(self):
        now = datetime.now(timezone.utc)
        account = {'user_id':'test-manager','role':'relationship_manager','auth_provider':'dossier',
                   'status':'approved','locked':False,'failed_attempts':0,'created_at':now,
                   'dossier_user_id':'test-manager','dossier_credential_version':1,
                   'password_hash':'must-not-be-returned','questions':'must-not-be-returned'}
        with patch('app.routers.auth.db_connection') as factory:
            factory.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = [account]
            response = self.client.get('/api/admin/users')
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['users'][0]['user_id'],'test-manager')
            self.assertNotIn('password_hash',response.json()['users'][0])
            self.assertNotIn('questions',response.json()['users'][0])
