import sys
from pathlib import Path
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from datetime import datetime,timezone
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import create_app
from app.config import ADMIN_USER_ID
from app.database import shared_policy_connection
from app.security import create_session,resolve_session,revoke_session


class DataManufacturingServerTests(unittest.TestCase):
    def test_generator_routes_are_only_available_in_dm(self):
        dm=create_app(initialize=False)
        with TestClient(dm) as client:
            schema=client.get('/openapi.json').json()['paths']
            self.assertIn('/api/data-manufacturing/policy-controls',schema)
            self.assertIn('/api/data-manufacturing/exceptions',schema)
            self.assertNotIn('/api/dashboard',schema)
            self.assertEqual(client.get('/api/health').json()['service'],'data-manufacturing')
            self.assertEqual(client.get('/api/data-manufacturing/policy-pdfs/status').status_code,401)
        # Read the CPI app by file path to avoid the two main.py module names.
        import importlib.util
        file=Path(__file__).resolve().parents[3]/'cpi_server'/'backend'/'main.py'
        spec=importlib.util.spec_from_file_location('cpi_main_for_dm_test',file)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        cpi_paths=module.app.openapi()['paths']
        self.assertIn('/api/dashboard',cpi_paths)
        self.assertFalse(any(path.startswith('/api/data-manufacturing') for path in cpi_paths))

    def test_dm_login_uses_its_own_cookies_and_csrf(self):
        app=create_app(initialize=False)
        user={'user_id':ADMIN_USER_ID,'role':'admin','status':'active','locked':False}
        session={'token':'dm-token','csrf_token':'dm-csrf','user':user,
                 'expires_at':datetime.now(timezone.utc).isoformat(),'session_minutes':15}
        with patch('app.routers.auth.ADMIN_PASSWORD','test-password'), \
             patch('app.routers.auth.create_session',return_value=session) as create, \
             patch('app.routers.auth.write_admin_log'), TestClient(app) as client:
            response=client.post('/api/auth/login',json={'user_id':ADMIN_USER_ID,'password':'test-password'})
            self.assertEqual(response.status_code,200,response.text)
            self.assertIn('dm_session',response.cookies)
            self.assertIn('dm_csrf',response.cookies)
            self.assertNotIn('cpi_session',response.cookies)
            self.assertNotIn('token',response.json())
            create.assert_called_once_with(user,'dm')

    def test_sessions_can_coexist_and_cannot_be_reused_across_apps(self):
        db=shared_policy_connection()
        self.addCleanup(db.close);self.addCleanup(db.rollback)
        @contextmanager
        def connection():yield db
        user={'user_id':ADMIN_USER_ID,'role':'admin'}
        def request(application,token,method='GET',csrf=''):
            app=FastAPI();app.state.application_id=application
            headers=[(b'cookie',f'{application}_session={token}'.encode())]
            if csrf:headers.append((b'x-csrf-token',csrf.encode()))
            return Request({'type':'http','method':method,'headers':headers,'app':app})
        with patch('app.security.db_connection',connection):
            cpi=create_session(user,'cpi');dm=create_session(user,'dm')
            self.assertEqual(resolve_session(request('cpi',cpi['token']))[1]['user']['user_id'],ADMIN_USER_ID)
            self.assertEqual(resolve_session(request('dm',dm['token']))[1]['user']['user_id'],ADMIN_USER_ID)
            with self.assertRaises(HTTPException):resolve_session(request('cpi',dm['token']))
            self.assertEqual(resolve_session(request('dm',dm['token']))[1]['user']['user_id'],ADMIN_USER_ID)
            with self.assertRaises(HTTPException):resolve_session(request('dm',dm['token'],'POST'))
            self.assertEqual(resolve_session(request('dm',dm['token'],'POST',dm['csrf_token']))[1]['user']['user_id'],ADMIN_USER_ID)
            revoke_session(dm['token'])
            self.assertEqual(resolve_session(request('cpi',cpi['token']))[1]['user']['user_id'],ADMIN_USER_ID)


if __name__=='__main__':unittest.main()
