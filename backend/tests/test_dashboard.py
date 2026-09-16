"""Dashboard integration tests using isolated account rows in the shared PostgreSQL schema."""
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql
from app.config import SESSIONS
from app.database import db_connection, account_user_id
from app.security import create_session
from tests.user_store_helpers import delete_test_user
from app.routers import dashboard


class DashboardTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(dashboard.router)
        self.client = TestClient(app)
        self.session = create_session({'user_id': 'dashboard-test-' + uuid4().hex, 'role': 'relationship_manager'})
        self.headers = {'Authorization': 'Bearer ' + self.session['token']}

    def tearDown(self):
        self.client.close()
        SESSIONS.pop(self.session['token'], None)
        with db_connection() as connection:
            delete_test_user(self.session['user']['user_id'])

    def get(self):
        response = self.client.get('/api/dashboard', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def get_portfolio(self):
        response = self.client.get('/api/portfolio', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_empty_and_authentication(self):
        self.assertEqual(self.client.get('/api/dashboard').status_code, 401)
        self.assertEqual(self.client.get('/api/portfolio').status_code, 401)
        self.assertEqual(self.client.post('/api/portfolio/chat', json={'question': 'Show concentration'}).status_code, 401)
        data = self.get()
        self.assertEqual(data['metrics']['open_exceptions'], 0)
        self.assertEqual(data['metrics']['exception_exposure'], 0)
        self.assertIsNone(data['metrics']['policy_compliance'])
        self.assertEqual(len(data['trend']), 6)
        self.assertEqual(sum(row['detected'] for row in data['trend']), 0)
        self.assertEqual(data['payments'], [])
        portfolio = self.get_portfolio()
        self.assertEqual(portfolio['sectors'], [])
        self.assertEqual(portfolio['geographies'], [])
        self.assertEqual(portfolio['rwa'], [])
        self.assertEqual(portfolio['clauses'], [])
        self.assertEqual(len(portfolio['trend']), 6)
        self.assertEqual(len(portfolio['ecl']), 6)

    def test_portfolio_chat_uses_current_account_snapshot(self):
        with patch('app.routers.dashboard.PortfolioChatAgent.run') as run:
            run.return_value = {
                'answer': 'There are no portfolio records in this account.',
                'agent': 'Mistral Credit Portfolio Analytics Agent',
            }
            response = self.client.post('/api/portfolio/chat', headers=self.headers, json={
                'question': 'What is the largest concentration?',
                'history': [
                    {'role': 'user', 'content': 'Summarize this portfolio'},
                    {'role': 'assistant', 'content': 'The portfolio is currently empty.'},
                ],
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['agent'], 'Mistral Credit Portfolio Analytics Agent')
        snapshot, question, history = run.call_args.args
        self.assertEqual(snapshot['sectors'], [])
        self.assertEqual(question, 'What is the largest concentration?')
        self.assertEqual(len(history), 2)

    def test_insights_replace_persist_and_isolate(self):
        self.assertEqual(self.client.post('/api/dashboard/insights').status_code, 401)
        self.assertEqual(self.get()['insights'], [])
        target = 'app.services.dashboard_agent.'
        with patch(target + 'PortfolioInsightsAgent._agent_id', return_value='test-agent'), \
                patch(target + 'Mistral'), patch(target + '_response_text', return_value='unused'), \
                patch(target + '_json_object') as generated:
            for prefix in ('First', 'Replacement'):
                points = [f'{prefix} point {n}' for n in range(6)]
                generated.return_value = {'insights': points}
                response = self.client.post('/api/dashboard/insights', headers=self.headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['insights'], points)
                self.assertEqual(self.get()['insights'], points)
                self.assertIsNotNone(self.get()['insights_generated_at'])
            for invalid in ([], ['too few'], ['duplicate'] * 5, [None] * 6):
                generated.return_value = {'insights': invalid}
                response = self.client.post('/api/dashboard/insights', headers=self.headers)
                self.assertEqual(response.status_code, 502, response.text)
                self.assertEqual(self.get()['insights'], points)
            generated.side_effect = RuntimeError('Provider unavailable')
            self.assertEqual(self.client.post('/api/dashboard/insights', headers=self.headers).status_code, 502)
            self.assertEqual(self.get()['insights'], points)
        other = create_session({'user_id': 'dashboard-test-' + uuid4().hex, 'role': 'relationship_manager'})
        try:
            response = self.client.get('/api/dashboard', headers={'Authorization': 'Bearer ' + other['token']})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['insights'], [])
        finally:
            SESSIONS.pop(other['token'], None)
            delete_test_user(other['user']['user_id'])
        token = account_user_id.set(self.session['user']['user_id'])
        try:
            with db_connection() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) AS n FROM dashboard_insights').fetchone()['n'], 1)
        finally:
            account_user_id.reset(token)

    def test_aggregates_and_refresh(self):
        self.get()
        token = account_user_id.set(self.session['user']['user_id'])
        try:
            with db_connection() as connection:
                borrower = connection.execute("INSERT INTO borrower (borrower_name) VALUES ('Dashboard Test') RETURNING borrower_id").fetchone()['borrower_id']
                connection.execute("""INSERT INTO credit_requests
                    (credit_request_number, borrower_id, borrower_name, industry, geography, exposure, facility, rating, requested_amount, status, compliance_score)
                    VALUES ('CR-TEST', %s, 'Dashboard Test', 'Manufacturing', 'US Northeast', 1000000, 'Term Loan', 'A', 1000000, 'In Review', 0)""", (borrower,))
                connection.execute("""INSERT INTO credit_request_compliance
                    (credit_request_number, geography_risk, concentration_limit_utilization,
                     adjusted_collateral, post_approval_exposure, approval_authority,
                     required_approval_authority, total_required_documents,
                     uploaded_required_documents, overall_score, compliance_status,
                     category_scores, findings, breached_rules, recommendations)
                    VALUES ('CR-TEST', 'High', 80, 1000000, 2000000, 'Credit Officer',
                            'Credit Officer', 1, 1, 80, 'Compliant', '{}', '[]', '[]', '[]')""")
                for number in range(2):
                    connection.execute("""INSERT INTO credit_request_exceptions
                        (exception_id, credit_request_number, exception_type, clause_code, severity, exposure, owner, due_date, status, description, rationale, workflow, history)
                        VALUES (%s, 'CR-TEST', 'Collateral', 'COL-1', 'High', 1000000, 'Test', CURRENT_DATE - 1, 'Active', 'Test', '{}', '[]', '[]')""", (f'EX-TEST-{number}',))
            data = self.get()
            self.assertEqual(data['metrics'], dict(active_requests=1, policy_compliance=0, open_exceptions=2, high_severity=2, overdue=2, exception_exposure=1000000))
            self.assertEqual(data['types'][0]['value'], 2000000)
            self.assertEqual(data['industries'][0]['value'], 2)
            self.assertEqual(data['trend'][-1]['detected'], 2)
            portfolio = self.get_portfolio()
            self.assertEqual(portfolio['sectors'][0]['label'], 'Manufacturing')
            self.assertEqual(float(portfolio['sectors'][0]['exposure_percent']), 100.0)
            self.assertEqual(portfolio['sectors'][0]['breaches'], 2)
            self.assertEqual(portfolio['geographies'][0]['label'], 'US Northeast')
            self.assertEqual(portfolio['geographies'][0]['risk'], 'High')
            self.assertEqual(float(portfolio['geographies'][0]['exposure_percent']), 100.0)
            self.assertEqual(portfolio['geographies'][0]['breaches'], 2)
            self.assertEqual(float(portfolio['rwa'][0]['value']), 0.5)
            self.assertEqual(portfolio['clauses'][0], {'label': 'COL-1', 'breaches': 2})
            other = create_session({'user_id': 'dashboard-test-' + uuid4().hex, 'role': 'relationship_manager'})
            try:
                response = self.client.get('/api/dashboard', headers={'Authorization': 'Bearer ' + other['token']})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['metrics']['active_requests'], 0)
                self.assertEqual(response.json()['metrics']['open_exceptions'], 0)
            finally:
                SESSIONS.pop(other['token'], None)
                with db_connection() as connection:
                    delete_test_user(other['user']['user_id'])
            with db_connection() as connection:
                connection.execute("""INSERT INTO borrower_exposure_history
                    (borrower_id, facility_reference, facility_type, reporting_month, original_exposure,
                     scheduled_payment, actual_payment, outstanding_exposure, days_past_due, payment_status)
                    VALUES (%s, 'F1', 'Term Loan', CURRENT_DATE - INTERVAL '1 month', 1000000, 0, 0, 1000000, 0, 'Current'),
                           (%s, 'F1', 'Term Loan', CURRENT_DATE, 1000000, 100000, 0, 900000, 30, 'Delayed')""", (borrower, borrower))
                connection.execute("""UPDATE credit_request_exceptions SET status='Closed', history=jsonb_build_array(jsonb_build_object('date', CURRENT_DATE::text, 'event', 'Closed exception'))""")
            data = self.get()
            self.assertEqual(data['metrics']['open_exceptions'], 0)
            self.assertEqual(data['metrics']['exception_exposure'], 0)
            self.assertEqual(data['trend'][-1]['remediated'], 2)
            self.assertEqual(data['payments'], [{'label': 'Delayed', 'value': 900000}])
            portfolio = self.get_portfolio()
            self.assertEqual(float(portfolio['ecl'][-1]['value']), 0.04)
        finally:
            account_user_id.reset(token)
