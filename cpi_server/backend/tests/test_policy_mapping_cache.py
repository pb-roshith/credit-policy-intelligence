import unittest
from unittest.mock import MagicMock, patch

from app.services import policy_mapping_cache as cache


class PolicyMappingCacheTests(unittest.TestCase):
    def setUp(self):
        self.user = {'user_id': 'owner-1'}
        self.report = {'policy_mappings': [], 'decisions': []}
        self.row = {'report': self.report, 'generated_at': 'saved-time'}
        self.connection = MagicMock()
        self.connection.execute.return_value.fetchone.return_value = self.row
        for name in ('db_connection', '_saved', 'assessment_request_context',
                     'latest_stored_compliance_review', 'policy_first_applicability', 'active_rule_candidates'):
            patcher = patch.object(cache, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.db_connection.return_value.__enter__.return_value = self.connection
        self.assessment_request_context.return_value = ('deal-1', {'status': 'Pending'})
        self.latest_stored_compliance_review.return_value = None
        self.policy_first_applicability.return_value = self.report

    def test_saved_mapping_skips_generation_and_remote_retrieval(self):
        self._saved.return_value = self.row
        result = cache.get_request_policy_mapping('deal-1', self.user)
        self.assertTrue(result['cached'])
        self.assessment_request_context.assert_not_called()
        self.policy_first_applicability.assert_not_called()
        self._saved.assert_called_once_with(self.connection, 'deal-1', 'owner-1')

    def test_first_selection_saves_even_an_empty_mapping(self):
        self._saved.return_value = None
        result = cache.get_request_policy_mapping('deal-1', self.user)
        self.assertFalse(result['cached'])
        self.policy_first_applicability.assert_called_once()
        query, params = self.connection.execute.call_args.args
        self.assertIn('INSERT INTO request_policy_mapping_cache', query)
        self.assertEqual(params[:2], ('owner-1', 'deal-1'))

    def test_concurrent_selection_rechecks_after_lock(self):
        self._saved.side_effect = [None, self.row]
        self.assertTrue(cache.get_request_policy_mapping('deal-1', self.user)['cached'])
        self.policy_first_applicability.assert_not_called()

    def test_existing_review_is_saved_without_generation(self):
        self._saved.return_value = None
        self.latest_stored_compliance_review.return_value = {'review_id': 7, 'applicability_report': self.report}
        cache.get_request_policy_mapping('deal-1', self.user)
        self.policy_first_applicability.assert_not_called()
        self.assertIn('"review_id": 7', self.connection.execute.call_args.args[1][2])

    def test_failed_generation_is_not_saved(self):
        self._saved.return_value = None
        self.policy_first_applicability.side_effect = RuntimeError('Provider unavailable')
        with self.assertRaises(RuntimeError):
            cache.get_request_policy_mapping('deal-1', self.user)
        self.assertFalse(any('INSERT INTO' in call.args[0] for call in self.connection.execute.call_args_list))
