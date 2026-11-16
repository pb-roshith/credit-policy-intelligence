"""Restored generator APIs and visibility, with all generated data rolled back."""
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql
from app.database import shared_policy_connection
from app.security import current_user
from app.manufacture_data import policy_controls,credit_requests
from app.routers.exceptions import exception_registry
from app.services.current_knowledge import manufactured_controls


class RestoredManufacturingTests(unittest.TestCase):
    def test_controls_can_be_generated_and_read_in_manufactured_register(self):
        db=shared_policy_connection()
        self.addCleanup(db.close);self.addCleanup(db.rollback)
        @contextmanager
        def connection():yield db
        app=FastAPI();app.include_router(policy_controls.router)
        from app.routers import policies
        app.include_router(policies.router)
        app.dependency_overrides[current_user]=lambda:{'user_id':'test-actor','role':'relationship_manager'}
        before={r['control_id']:dict(r) for r in db.execute('SELECT * FROM policy_controls').fetchall()}
        before_counts={r['policy_id']:r['n'] for r in db.execute('SELECT policy_id,COUNT(*) AS n FROM policy_controls GROUP BY policy_id').fetchall()}
        with patch('app.manufacture_data.policy_controls.shared_policy_connection',connection), \
             patch('app.database.shared_policy_connection',connection), TestClient(app) as client:
            first=client.post('/api/data-manufacturing/policy-controls',json={'controls_per_policy':5})
            self.assertEqual(first.status_code,201,first.text)
            checkpoint={r['control_id']:dict(r) for r in db.execute('SELECT * FROM policy_controls').fetchall()}
            second=client.post('/api/data-manufacturing/policy-controls',json={'controls_per_policy':2})
            self.assertEqual(second.status_code,201,second.text)
            result=second.json();rows=manufactured_controls()
            self.assertEqual(result['added_count'],result['policy_count']*2)
            self.assertEqual(result['control_count'],len(before)+result['policy_count']*7)
            for policy_id in {r['policy_id'] for r in rows}:
                mapped=client.get(f'/api/policies/{policy_id}/controls')
                self.assertEqual(mapped.status_code,200)
                self.assertEqual(len(mapped.json()),before_counts.get(policy_id,0)+7)
            after={r['control_id']:dict(r) for r in db.execute('SELECT * FROM policy_controls').fetchall()}
            for identifier,row in before.items():self.assertEqual(after[identifier],row)
            for identifier,row in checkpoint.items():self.assertEqual(after[identifier],row)
        self.assertTrue(all(r['synthetic'] and not r['published_in_graph'] for r in rows))

    def test_generated_exception_is_visible_to_its_owner(self):
        db=shared_policy_connection()
        self.addCleanup(db.close);self.addCleanup(db.rollback)
        source=db.execute("""SELECT u.user_id,cr.credit_request_number FROM public.users u
            JOIN "user".credit_requests cr USING(user_id) WHERE u.role='relationship_manager'
            ORDER BY u.user_id,cr.credit_request_number LIMIT 1""").fetchone()
        user={'user_id':source['user_id'],'role':'relationship_manager'}
        db.execute(sql.SQL('SET LOCAL app.user_id TO {}').format(sql.Literal(user['user_id'])))
        db.execute('SET LOCAL ROLE credit_user_runtime');db.execute('SET LOCAL search_path TO "user"')
        @contextmanager
        def connection():yield db
        app=FastAPI();app.include_router(credit_requests.router)
        app.dependency_overrides[current_user]=lambda:user
        with patch('app.manufacture_data.credit_requests.db_connection',connection), \
             patch('app.routers.exceptions.db_connection',connection), TestClient(app) as client:
            response=client.post('/api/data-manufacturing/exceptions',json={'credit_request_numbers':[source['credit_request_number']]})
            self.assertEqual(response.status_code,201,response.text)
            created=response.json()['exceptions'][0]
            visible=exception_registry(_=user)
        row=next(r for r in visible if r['id']==created['id'])
        self.assertEqual(row['account_user_id'],user['user_id'])
        self.assertTrue(row['rationale']['synthetic'])
        self.assertEqual(row['rationale']['data_origin'],'DATA_MANUFACTURING')
