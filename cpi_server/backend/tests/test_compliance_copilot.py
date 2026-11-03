import json
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from mistralai.client.errors import SDKError

from app.routers.compliance import compliance_review_copilot
from app.schemas import ComplianceCopilotRequest
from app.services.compliance_copilot import copilot_prompt


class CopilotContextTests(unittest.TestCase):
    def test_large_nested_evidence_is_excluded_but_table_values_remain(self):
        prompt = copilot_prompt({'findings': [{
            'rule_name': 'Collateral check', 'actual': '40%', 'threshold': '60%',
            'result': 'Breach', 'evidence_references': ['x' * 4_000_000],
        }]}, 'Why did collateral breach?')
        self.assertLess(len(prompt), 3000)
        self.assertIn('40%', prompt)
        self.assertIn('60%', prompt)
        self.assertNotIn('evidence_references', prompt)

    def test_context_budget_retains_totals_and_prioritizes_requested_rule(self):
        findings = [{'rule_name': f'Rule {i}', 'result': 'Pass', 'actual': 'x' * 300,
                     'threshold': 'y' * 300} for i in range(1000)]
        findings.append({'rule_name': 'SPECIAL-DSCR', 'result': 'Breach', 'actual': '0.5'})
        prompt = copilot_prompt({'findings': findings}, 'Explain SPECIAL-DSCR')
        self.assertLess(len(prompt), 50000)
        context = json.loads(prompt.split('Assessment:\n')[1].split('\n\nUser question:')[0])
        self.assertEqual(context['result_counts'], {'Pass': 1000, 'Breach': 1})
        self.assertEqual(context['findings'][0]['rule_name'], 'SPECIAL-DSCR')
        self.assertGreater(context['omitted_findings'], 0)


class CopilotRequestTests(unittest.TestCase):
    def ask(self, outcomes, review=None):
        with patch('app.routers.compliance.MISTRAL_API_KEY', 'test'), \
             patch('app.routers.compliance.latest_stored_compliance_review', return_value=review), \
             patch('app.routers.compliance.observe_ai', return_value=nullcontext({})), \
             patch('app.routers.compliance.Mistral') as factory, \
             patch('app.routers.compliance.sleep'):
            complete = factory.return_value.__enter__.return_value.chat.complete
            complete.side_effect = outcomes
            try:
                return compliance_review_copilot(ComplianceCopilotRequest(
                    credit_request_number='CR-1', question='What failed?'), {'user_id': 'manager'})
            finally:
                self.calls = complete.call_count
                factory.return_value.__enter__.return_value.beta.conversations.start.assert_not_called()

    def response(self, answer):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'answer': answer})))])

    def test_direct_completion_returns_answer(self):
        self.assertEqual(self.ask([self.response('No breaches.')], {'findings': []})['answer'], 'No breaches.')
        self.assertEqual(self.calls, 1)

    def test_rate_limit_retries_then_succeeds(self):
        error = SDKError('Rate limit', httpx.Response(429))
        self.assertEqual(self.ask([error, self.response('Review the breach.')], {'findings': []})['answer'], 'Review the breach.')
        self.assertEqual(self.calls, 2)

    def test_persistent_rate_limit_returns_actionable_message(self):
        error = SDKError('Rate limit', httpx.Response(429))
        with self.assertRaises(HTTPException) as caught:
            self.ask([error, error], {'findings': []})
        self.assertEqual(caught.exception.status_code, 429)
        self.assertIn('rate-limited', caught.exception.detail)

    def test_missing_current_review_does_not_call_provider(self):
        with self.assertRaises(HTTPException) as caught:
            self.ask([])
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.calls, 0)

    def test_invalid_provider_answer_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            self.ask([self.response(None)], {'findings': []})
        self.assertEqual(caught.exception.status_code, 502)
