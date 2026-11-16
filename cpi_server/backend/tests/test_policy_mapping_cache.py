import unittest
from unittest.mock import MagicMock, patch
from app.services.policy_mapping_cache import get_request_policy_mapping


class CurrentMappingTests(unittest.TestCase):
    def test_always_validates_request_and_recomputes_against_current_knowledge(self):
        connection = MagicMock()
        connection.__enter__.return_value.execute.return_value.fetchone.return_value = {'generated_at':'now'}
        report = {'applicability_version':'graph-applicability-v1','decisions':[],'policy_mappings':[]}
        with patch('app.services.policy_mapping_cache.assessment_request_context', return_value=('deal-1',{'status':'Pending'})) as context, \
             patch('app.services.policy_mapping_cache.load_matcher') as load, \
             patch('app.services.policy_mapping_cache.db_connection', return_value=connection):
            load.return_value.match.return_value=report
            result = get_request_policy_mapping('deal-1',{'user_id':'owner'})
        context.assert_called_once_with('deal-1',{'user_id':'owner'})
        load.return_value.match.assert_called_once_with({'status':'Pending'})
        self.assertFalse(result['cached'])
        self.assertIn('ON CONFLICT', connection.__enter__.return_value.execute.call_args.args[0])

    def test_failed_request_access_never_loads_shared_knowledge(self):
        with patch('app.services.policy_mapping_cache.assessment_request_context', side_effect=RuntimeError('Denied')), \
             patch('app.services.policy_mapping_cache.load_matcher') as evaluate:
            with self.assertRaises(RuntimeError): get_request_policy_mapping('other-deal',{'user_id':'owner'})
        evaluate.assert_not_called()


if __name__ == '__main__': unittest.main()
