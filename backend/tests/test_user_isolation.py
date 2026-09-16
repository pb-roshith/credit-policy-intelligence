"""Integration checks against the configured PostgreSQL database.

Run: python -m unittest discover -s tests -v
Only rows owned by randomly named test accounts are created and removed.
"""
import unittest
import psycopg
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql

from app.database import db_connection, shared_policy_connection, account_user_id
from app.security import create_session
from tests.user_store_helpers import delete_test_user
from app.config import SESSIONS
from app.routers import requests, policies, controls
from app.manufacture_data import credit_requests, exposure_history, policy_pdfs
from app.routers import exceptions


class UserIsolationTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        for module in (requests, policies, controls, credit_requests, exposure_history, policy_pdfs, exceptions):
            app.include_router(module.router)
        self.client = TestClient(app)
        self.sessions = [create_session({"user_id": "isolation-test-" + uuid4().hex,
                                        "role": role})
                         for role in ("relationship_manager", "relationship_manager", "admin")]
        self.shared_job_id = "shared-test-" + uuid4().hex[:16]

    def tearDown(self):
        self.client.close()
        with db_connection() as connection:
            for session in self.sessions:
                SESSIONS.pop(session["token"], None)
                delete_test_user(session["user"]["user_id"])

        with shared_policy_connection() as connection:
            connection.execute("DELETE FROM policy_generation_jobs WHERE job_id = %s", (self.shared_job_id,))

    def call(self, account, method, path, **kwargs):
        return self.client.request(method, path, headers={
            "Authorization": "Bearer " + self.sessions[account]["token"]
        }, **kwargs)

    def test_generated_requests_and_related_data_are_private(self):
        response = self.call(0, "POST", "/api/data-manufacturing/credit-requests", json={"count": 2})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(all(row['geography'] for row in response.json()['credit_requests']))
        number = response.json()["credit_requests"][0]["credit_request_number"]
        for account in (1, 2):
            self.assertEqual(self.call(account, "GET", "/api/requests").json(), [])
            self.assertEqual(self.call(account, "GET", "/api/summary").json()["active_requests"], 0)
            self.assertEqual(self.call(account, "GET", f"/api/requests/{number}/compliance-score").status_code, 404)
            self.assertEqual(self.call(account, "POST", "/api/data-manufacturing/borrower-exposure-history",
                                       json={"records_per_borrower": 6}).status_code, 422)
        self.assertEqual(len(self.call(0, "GET", "/api/requests").json()), 2)
        self.assertEqual(self.call(0, "GET", f"/api/requests/{number}/compliance-score").status_code, 200)
        self.assertEqual(self.call(0, "POST", "/api/data-manufacturing/borrower-exposure-history",
                                   json={"records_per_borrower": 6}).status_code, 201)
        response = self.call(1, "POST", "/api/data-manufacturing/credit-requests", json={"count": 1})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(self.call(1, "GET", "/api/requests").json()), 1)
        self.assertEqual(len(self.call(0, "GET", "/api/requests").json()), 2)
        self.assertEqual(self.client.get("/api/requests").status_code, 401)

    def test_policy_intelligence_is_shared_across_roles(self):
        with shared_policy_connection() as connection:
            connection.execute("""INSERT INTO policy_generation_jobs
                (job_id, status, total_documents, message, initiated_by)
                VALUES (%s, 'completed', 35, 'Shared generation', %s)""",
                (self.shared_job_id, self.sessions[0]["user"]["user_id"]))
        expected_policies = self.call(0, "GET", "/api/policies").json()
        for account in (1, 2):
            response = self.call(account, "GET", f"/api/data-manufacturing/policy-pdfs/{self.shared_job_id}")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.call(account, "GET", "/api/policies").json(), expected_policies)

    def test_manual_requests_are_private(self):
        payload = {
            "borrower_name": "Private Borrower", "industry": "Manufacturing",
            "geography": "Asia Pacific",
            "facility": "Term Loan", "rating": "A", "requested_amount": 1000000,
            "status": "In Review", "geography_risk": "Low",
            "concentration_limit_utilization": 10, "adjusted_collateral": 1000000,
            "approval_authority": "Credit Officer", "total_required_documents": 1,
            "uploaded_required_documents": 1,
            "policy_clauses": [{"clause_code": "CP-4.2", "clause_name": "Leverage", "result": "PASS"}],
        }
        response = self.call(0, "POST", "/api/requests", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['geography'], 'Asia Pacific')
        self.assertEqual(self.call(1, "GET", "/api/requests").json(), [])
        # Identical borrower names are independent in each account.
        response = self.call(1, "POST", "/api/requests", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(self.call(0, "GET", "/api/requests").json()), 1)

    def test_database_rejects_cross_account_writes_and_references(self):
        response = self.call(0, 'POST', '/api/data-manufacturing/credit-requests', json={'count': 1})
        self.assertEqual(response.status_code, 201, response.text)
        request = response.json()['credit_requests'][0]
        scope = account_user_id.set(self.sessions[1]['user']['user_id'])
        try:
            with db_connection() as c:
                self.assertEqual(c.execute('SELECT count(*) AS n FROM credit_requests').fetchone()['n'], 0)
                self.assertEqual(c.execute('UPDATE credit_requests SET status=\'Approved\'').rowcount, 0)
                self.assertEqual(c.execute('DELETE FROM credit_requests').rowcount, 0)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with db_connection() as c:
                    c.execute('INSERT INTO borrower (user_id, borrower_name) VALUES (%s, %s)',
                              (self.sessions[0]['user']['user_id'], 'Forbidden'))
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with db_connection() as c:
                    c.execute("""INSERT INTO credit_request_policy_evaluations
                        (credit_request_number, clause_code, clause_name, result)
                        VALUES (%s, 'TEST', 'Cross-account reference', 'PASS')""", (request['credit_request_number'],))
        finally:
            account_user_id.reset(scope)
        self.assertEqual(len(self.call(0, 'GET', '/api/requests').json()), 1)

    def test_selected_requests_generate_account_scoped_exceptions(self):
        for account in (0, 1):
            response = self.call(account, 'POST', '/api/data-manufacturing/credit-requests', json={'count': 1})
            self.assertEqual(response.status_code, 201, response.text)
            request_number = response.json()['credit_requests'][0]['credit_request_number']
            response = self.call(account, 'GET', '/api/exceptions')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), [])
            response = self.call(account, 'POST', '/api/data-manufacturing/exceptions', json={
                'credit_request_numbers': [request_number],
            })
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()['count'], 1)
            registry = self.call(account, 'GET', '/api/exceptions').json()
            self.assertEqual(len(registry), 1)
            self.assertEqual(registry[0]['credit_request_number'], request_number)
        self.assertEqual(self.call(2, 'GET', '/api/exceptions').json(), [])

if __name__ == "__main__":
    unittest.main()

