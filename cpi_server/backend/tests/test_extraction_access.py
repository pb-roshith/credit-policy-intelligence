import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fastapi import BackgroundTasks, HTTPException
from app.routers import rules
from app.services.rule_extraction import process_policy


class ExtractionAccessTests(unittest.TestCase):
    def test_new_jobs_reextract_completed_documents_with_separate_checkpoints(self):
        checkpoint_keys = []
        connection = MagicMock()
        def execute(query, params=None):
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = {'n': 0}
            if 'FROM policy_extraction_reports' in query:
                result.fetchone.return_value = {'exists': 1}
            if 'SELECT * FROM rule_extraction_batches' in query:
                checkpoint_keys.append(params[0])
                result.fetchone.return_value = None
            return result
        connection.execute.side_effect = execute
        with patch('app.services.rule_extraction.ingest_policy', return_value=(
            {'title': 'Existing policy'}, {'id': 1}, {'id': 2, 'extraction_status': 'Completed'},
            [{'id': 3, 'source_excerpt': 'Exposure must not exceed 100 USD.'}]
        )), patch('app.services.rule_extraction.shared_policy_connection') as factory, \
             patch('app.services.rule_extraction.extract_batch', return_value=SimpleNamespace(rules=[])) as extract:
            factory.return_value.__enter__.return_value = connection
            for job_id in ('first-job', 'second-job'):
                result = process_policy(3, {'role': 'credit_analyst', 'user_id': 'reviewer'}, job_id)
                self.assertNotEqual(result['status'], 'Already processed')
            self.assertEqual(extract.call_count, 2)
        self.assertNotEqual(checkpoint_keys[0], checkpoint_keys[2])

    def test_business_roles_can_extract_selected_policies(self):
        for role in ('relationship_manager', 'credit_analyst'):
            with self.subTest(role=role), patch.object(rules, 'enqueue_inventory', return_value={'id': 'job-1'}) as enqueue:
                user = {'role': role, 'user_id': 'reviewer'}
                background = BackgroundTasks()
                result = rules.generate(rules.InventoryJobInput(policy_ids=[3, 7]), background, user)
                enqueue.assert_called_once_with(user, [3, 7])
                self.assertEqual(result['id'], 'job-1')
                self.assertEqual(len(background.tasks), 1)

    def test_business_roles_must_select_documents(self):
        for role in ('relationship_manager', 'credit_analyst'):
            with self.subTest(role=role), patch.object(rules, 'enqueue_inventory') as enqueue:
                with self.assertRaises(HTTPException) as error:
                    rules.generate(rules.InventoryJobInput(policy_ids=[]), BackgroundTasks(), {'role': role})
                self.assertEqual(error.exception.status_code, 422)
                enqueue.assert_not_called()

    def test_unavailable_role_cannot_extract(self):
        with self.assertRaises(HTTPException) as error:
            rules.generate(rules.InventoryJobInput(policy_ids=[3]), BackgroundTasks(), {'role': 'viewer'})
        self.assertEqual(error.exception.status_code, 403)

    def test_document_without_quantitative_rules_is_not_completed(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {'n': 0}
        connection.execute.return_value.fetchall.return_value = []
        with patch('app.services.rule_extraction.ingest_policy', return_value=(
            {'title': 'Qualitative policy'}, {'id': 1}, {'id': 2, 'extraction_status': 'Pending'}, []
        )), patch('app.services.rule_extraction.shared_policy_connection') as factory:
            factory.return_value.__enter__.return_value = connection
            result = process_policy(3, {'role': 'credit_analyst', 'user_id': 'reviewer'})
        self.assertEqual(result['status'], 'Failed')
        self.assertEqual(result['quantitative_rules'], 0)
        self.assertIn('At least one source-backed quantitative rule', result['error'])
