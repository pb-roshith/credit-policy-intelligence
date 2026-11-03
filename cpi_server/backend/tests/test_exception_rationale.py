import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
import httpx
from mistralai.client.errors import SDKError

from app.services.exception_rationale import generate_exception_rationale, _review_context, _retry_delay


class ExceptionRationaleTests(unittest.TestCase):
    def generate(self, outcomes):
        with patch('app.services.exception_rationale.MISTRAL_API_KEY', 'test'), \
             patch('app.services.exception_rationale.observe_ai', return_value=nullcontext({})), \
             patch('app.services.exception_rationale.Mistral') as factory, \
             patch('app.services.exception_rationale.sleep') as delay:
            complete = factory.return_value.__enter__.return_value.chat.complete
            complete.side_effect = outcomes
            try:
                return generate_exception_rationale({}, {}, None, 'manager')
            finally:
                self.calls = complete.call_count
                self.delays = delay.call_count

    def rate_limit(self):
        return SDKError('Rate limit exceeded', httpx.Response(429))

    def test_rate_limit_recovers_without_duplicate_creation(self):
        content = '{"why_detected":"Deviation","business_justification":"Review needed","risk_implication":"Risk","recommended_remediation":"Review","escalation_required":"Analyst approval"}'
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        result = self.generate([self.rate_limit(), response])
        self.assertEqual(result['why_detected'], 'Deviation')
        self.assertEqual((self.calls, self.delays), (2, 1))

    def test_persistent_rate_limit_returns_clearly_pending_rationale(self):
        result = self.generate([self.rate_limit() for _ in range(3)])
        self.assertEqual(result['generation_status'], 'pending')
        self.assertIn('Exception saved', result['generation_notice'])
        self.assertIn('Not yet assessed', result['risk_implication'])
        self.assertEqual((self.calls, self.delays), (3, 2))

    def test_other_provider_errors_are_not_retried(self):
        with self.assertRaises(HTTPException) as caught:
            self.generate([RuntimeError('Provider unavailable')])
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual((self.calls, self.delays), (1, 0))

    def test_large_assessment_context_is_bounded_and_matches_clause(self):
        import json
        review = {'findings': [
            {'policy_clause': 'OTHER', 'result': 'BREACH', 'provenance': 'x' * 4_000_000},
            {'policy_clause': 'POL-1', 'actual': 15, 'threshold': 10, 'evidence': 'a' * 4_000_000},
        ]}
        context = _review_context(review, {'clause': 'POL-1'})
        self.assertLess(len(json.dumps(context)), 3000)
        self.assertEqual(len(context['findings']), 1)
        self.assertEqual(context['findings'][0]['actual'], '15')
        self.assertEqual(context['findings'][0]['threshold'], '10')
        self.assertEqual(context['findings_in_saved_review'], 2)

    def test_retry_honors_provider_cooldown(self):
        error = SDKError('Rate limit exceeded', httpx.Response(429, headers={'Retry-After': '25'}))
        self.assertEqual(_retry_delay(error, 0), 25)
        self.assertEqual(_retry_delay(self.rate_limit(), 0), 10)
        self.assertEqual(_retry_delay(self.rate_limit(), 1), 20)

    def test_long_provider_cooldown_does_not_block_creation(self):
        error = SDKError('Rate limit exceeded', httpx.Response(429, headers={'Retry-After': '120'}))
        result = self.generate([error])
        self.assertEqual(result['generation_status'], 'pending')
        self.assertEqual((self.calls, self.delays), (1, 0))
