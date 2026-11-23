"""Shared identity integration tests; fixture writes are rolled back."""
import hashlib
import unittest
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.database import SessionLocal, get_db, engine
from app.config import settings
from app.migrations import apply_additive_migrations
from app.models.user import User, AuthSession
from app.auth import verify_password
from app.routers.auth import router as auth_router
from app.routers.shared_deals import router as shared_router


class SharedIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_additive_migrations(engine)

    def setUp(self):
        self.db = SessionLocal()
        self.addCleanup(self.db.close)
        self.addCleanup(self.db.rollback)
        self.commit = patch.object(self.db, 'commit', self.db.flush)
        self.commit.start()
        self.addCleanup(self.commit.stop)
        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(shared_router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.key = patch.object(settings, 'SHARED_DEAL_API_KEY', 'identity-test-key')
        self.key.start()
        self.addCleanup(self.key.stop)
        self.headers = {'X-Shared-Deal-Key': 'identity-test-key'}
        self.name = 'identity_' + uuid4().hex[:12]
        self.password = 'SyntheticOnly!123456'
        self.answers = [{'question': question, 'answer': 'test answer'} for question in ('First test question?', 'Second test question?', 'Third test question?')]
        self.registration = {'user_id':self.name, 'password':self.password, 'confirm_password':self.password, 'role':'relationship_manager','security_questions':self.answers}

    def shared(self, action, payload):
        return self.client.post('/api/shared/deals/identity/' + action, headers=self.headers, json=payload)

    def create(self, via_shared=True):
        response = self.shared('register', self.registration) if via_shared else self.client.post('/api/auth/register', json=self.registration)
        self.assertEqual(response.status_code, 201, response.text)
        return self.db.query(User).filter_by(user_id=self.name).one()

    def test_registration_from_either_app_uses_one_case_insensitive_namespace(self):
        for via_shared in (True, False):
            with self.subTest(via_shared=via_shared):
                self.name = 'identity_' + uuid4().hex
                self.registration['user_id'] = self.name
                self.create(via_shared)
                duplicate = {**self.registration, 'user_id':self.name.upper()}
                self.assertEqual(self.shared('register',duplicate).status_code,409)
                self.assertEqual(self.client.post('/api/auth/register',json=duplicate).status_code,409)
                self.assertEqual(self.db.query(User).filter_by(user_id=self.name).count(),1)
                pending = self.shared('authenticate',{'user_id':self.name,'password':self.password})
                self.assertEqual(pending.status_code,403)
                self.assertEqual(self.shared('approve',{'user_id':self.name}).status_code,200)
                self.assertEqual(self.shared('authenticate',{'user_id':self.name.upper(),'password':self.password}).status_code,200)
                self.assertEqual(self.client.post('/api/auth/login',json={'user_id':self.name,'password':self.password}).status_code,200)

    def test_reset_from_each_app_changes_shared_password_and_revokes_sessions(self):
        user = self.create()
        self.shared('approve',{'user_id':self.name})
        self.client.post('/api/auth/login',json={'user_id':self.name,'password':self.password})
        self.assertEqual(self.db.query(AuthSession).filter_by(user_id=user.id).count(),1)
        expected_questions = [answer['question'] for answer in self.answers]
        self.assertEqual(self.shared('questions',{'user_id':self.name}).json()['questions'],expected_questions)
        self.assertEqual(self.client.post('/api/auth/reset-password/questions',json={'user_id':self.name}).json()['questions'],expected_questions)
        for index, shared in enumerate((True,False),2):
            new_password = 'ChangedOnly!12345' + str(index)
            payload = {'user_id':self.name,'new_password':new_password,'confirm_password':new_password,'security_questions':self.answers}
            result = self.shared('reset-password',payload) if shared else self.client.post('/api/auth/reset-password',json=payload)
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(user.credential_version,index)
            self.assertEqual(self.db.query(AuthSession).filter_by(user_id=user.id).count(),0)
            self.assertEqual(self.shared('authenticate',{'user_id':self.name,'password':new_password}).status_code,200)
            self.assertEqual(self.client.post('/api/auth/login',json={'user_id':self.name,'password':new_password}).status_code,200)
            self.assertFalse(verify_password(self.password,user.password_hash))
            self.password = new_password

    def test_recovery_cannot_reset_without_correct_answers(self):
        user = self.create()
        self.shared('approve',{'user_id':self.name})
        result = self.shared('reset-password',{'user_id':self.name,'new_password':'ChangedOnly!123456','confirm_password':'ChangedOnly!123456','security_questions':[{**answer,'answer':'wrong'} for answer in self.answers]})
        self.assertEqual(result.status_code,400)
        self.assertEqual(user.credential_version,1)
        self.assertTrue(verify_password(self.password,user.password_hash))

    def test_import_keeps_cpi_hashes_and_replaces_only_authorized_duplicate(self):
        user = self.create(False)
        original_id = user.id
        salt = bytes.fromhex('0123456789abcdef0123456789abcdef')
        def cpi_hash(value):
            return salt.hex()+':'+hashlib.pbkdf2_hmac('sha256',value.encode(),salt,310000).hex()
        payload = {'user_id':self.name,'source_id':self.name,'password_hash':cpi_hash('ImportedOnly!123456'), 'role':'credit_analyst','approved':True,'locked':False,'security_answers':[{'question':a['question'],'answer_hash':cpi_hash(a['answer'])} for a in self.answers]}
        self.assertEqual(self.shared('import',payload).status_code,409)
        payload['replace_existing'] = True
        result = self.shared('import',payload)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(user.id,original_id)
        self.assertEqual(user.role,'credit_analyst')
        self.assertTrue(verify_password('ImportedOnly!123456',user.password_hash))
        self.assertFalse(verify_password(self.password,user.password_hash))
        reset = self.shared('reset-password', {'user_id':self.name,
            'new_password':'AfterImport!123456','confirm_password':'AfterImport!123456',
            'security_questions':self.answers})
        self.assertEqual(reset.status_code,200,reset.text)
        self.assertEqual(self.shared('import',payload).json()['status'],'already_imported')
        self.assertTrue(verify_password('AfterImport!123456',user.password_hash))

    def test_identity_operations_require_service_key(self):
        for action,payload in [('register',self.registration),('approve',{'user_id':self.name}),('questions',{'user_id':self.name}),('reset-password',{'user_id':self.name,'new_password':self.password,'confirm_password':self.password,'security_questions':self.answers})]:
            self.assertEqual(self.client.post('/api/shared/deals/identity/'+action,json=payload).status_code,401)
