import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import copy_context
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from app.database import account_user_id
from app.telemetry import account_ai_job, record_ai_call, _usage, _response_text


class AIObservabilityTests(unittest.TestCase):
    def setUp(self):
        token = account_user_id.set('manager')
        self.addCleanup(account_user_id.reset, token)

    def test_provider_response_is_captured_with_measured_usage_and_input(self):
        response = SimpleNamespace(model_dump=lambda **kwargs: {
            'usage': {'prompt_tokens': 40, 'completion_tokens': 10, 'total_tokens': 50}})
        capture = {}

        @contextmanager
        def observer(*args, **kwargs):
            self.assertEqual(args[:3], ('Risk Knowledge', 'knowledge_taxonomy_mapping', 'manager'))
            self.assertIn('source excerpt', kwargs['input_payload'])
            self.assertNotIn('secret-key', kwargs['input_payload'])
            yield capture

        with patch('app.telemetry.observe_ai', side_effect=observer):
            result = record_ai_call('Risk Knowledge', 'knowledge_taxonomy_mapping', Mock(return_value=response),
                                    model='configured-model', messages=[{'content': 'source excerpt'}],
                                    headers={'Authorization': 'secret-key'})
        self.assertIs(result, response)
        self.assertIs(capture['response'], response)
        self.assertEqual(_usage(response), (40, 10, 50))

    def test_provider_failure_reaches_telemetry_and_preserves_error(self):
        failures = []

        @contextmanager
        def observer(*args, **kwargs):
            try:
                yield {}
            except RuntimeError as error:
                failures.append(str(error))
                raise

        with patch('app.telemetry.observe_ai', side_effect=observer), self.assertRaises(RuntimeError):
            record_ai_call('Policy Rule Library', 'rule_extraction', Mock(side_effect=RuntimeError('unavailable')))
        self.assertEqual(failures, ['unavailable'])

    def test_configurable_provider_usage_and_output_are_captured(self):
        response = httpx.Response(200, json={
            'usage': {'prompt_tokens': 8, 'completion_tokens': 2, 'total_tokens': 10},
            'choices': [{'message': {'content': '{"items":[]}'}}]})
        self.assertEqual(_usage(response), (8, 2, 10))
        self.assertEqual(_response_text(response), '{"items":[]}')

    def test_background_job_and_worker_keep_initiating_account(self):
        @account_ai_job
        def job(job_id, user):
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(copy_context().run, account_user_id.get).result()

        self.assertEqual(job('job-1', {'user_id': 'other-manager'}), 'other-manager')
        self.assertEqual(account_user_id.get(), 'manager')

    def test_offline_scripts_do_not_record_under_another_account(self):
        account_user_id.set(None)
        with patch('app.telemetry.observe_ai') as observer:
            self.assertEqual(record_ai_call('Risk Knowledge', 'knowledge_rule_extraction', lambda: 42), 42)
            observer.assert_not_called()
