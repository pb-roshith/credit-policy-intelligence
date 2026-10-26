import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
import httpx
from mistralai.client.errors import SDKError

from app.services.exception_rationale import generate_exception_rationale


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

    def test_persistent_rate_limit_has_actionable_response(self):
        with self.assertRaises(HTTPException) as caught:
            self.generate([self.rate_limit() for _ in range(3)])
        self.assertEqual(caught.exception.status_code, 429)
        self.assertIn('has not been created', caught.exception.detail)
        self.assertEqual(caught.exception.headers['Retry-After'], '60')
        self.assertEqual((self.calls, self.delays), (3, 2))

    def test_other_provider_errors_are_not_retried(self):
        with self.assertRaises(HTTPException) as caught:
            self.generate([RuntimeError('Provider unavailable')])
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual((self.calls, self.delays), (1, 0))
