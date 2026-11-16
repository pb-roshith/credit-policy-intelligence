import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fastapi import BackgroundTasks, HTTPException
from app.routers import rules
from app.services.rule_extraction import process_policy


class ExtractionAccessTests(unittest.TestCase):
    def test_new_jobs_reextract_completed_documents_with_separate_checkpoints(self):
        with patch('app.risk_knowledge.semantic_pipeline.process_policy',return_value={'status':'Completed'}) as graph_first, \
             patch('app.services.rule_extraction.extract_batch') as extract:
            for job_id in ('first-job', 'second-job'):
                result = process_policy(3, {'role': 'credit_analyst', 'user_id': 'reviewer'}, job_id)
                self.assertNotEqual(result['status'], 'Already processed')
        self.assertEqual(graph_first.call_count,2)
        self.assertNotEqual(graph_first.call_args_list[0].args[2],graph_first.call_args_list[1].args[2])
        extract.assert_not_called()

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

    def test_unresolved_policy_is_returned_as_incomplete_instead_of_inventing_quantitative_rules(self):
        expected={'status':'Completed with errors','quantitative_rules':0,'unresolved_spans':3}
        with patch('app.risk_knowledge.semantic_pipeline.process_policy',return_value=expected), \
             patch('app.services.rule_extraction.extract_batch') as extract:
            result=process_policy(3,{'role':'credit_analyst','user_id':'reviewer'})
        self.assertEqual(result,expected)
        extract.assert_not_called()
