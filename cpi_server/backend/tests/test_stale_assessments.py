import unittest
from unittest.mock import patch

from app.services.compliance_agent import latest_stored_compliance_review


class StaleAssessmentTests(unittest.TestCase):
    def load_review(self, retained):
        with patch('app.services.compliance_agent.db_connection') as scoped, \
             patch('app.services.compliance_agent.shared_policy_connection') as shared, \
             patch('app.services.assessment_comparison.refresh_finding_comparisons', side_effect=lambda review: review):
            scoped.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {
                'review_id': 7, 'created_at': '2026-11-02',
                'review': {'rule_snapshots': [{'id': 10}], 'findings': [{'rule_version_id': 11}]},
            }
            shared.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = [
                {'id': identifier} for identifier in retained]
            return latest_stored_compliance_review('CR-1')

    def test_removed_snapshot_invalidates_saved_totals(self):
        self.assertIsNone(self.load_review([11]))

    def test_removed_finding_invalidates_saved_totals(self):
        self.assertIsNone(self.load_review([10]))

    def test_retained_legacy_rules_do_not_reinstate_earlier_assessment_method(self):
        self.assertIsNone(self.load_review([10,11]))

    def test_semantic_ids_are_not_cast_to_legacy_numeric_rule_ids(self):
        from types import SimpleNamespace
        review={'assessment_scope':'current-semantic-graph','knowledge_fingerprint':'current',
                'rule_snapshots':[{'id':'urn:cpi:rule:v7:clause1:r1'}]}
        from app.services.semantic_assessment import ENGINE_VERSION
        review['engine_version']=ENGINE_VERSION
        with patch('app.services.compliance_agent.db_connection') as db, \
             patch('app.services.semantic_matching.load_matcher',return_value=SimpleNamespace(fingerprint='current')):
            db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'review_id':1,'created_at':'today','review':review}
            result=latest_stored_compliance_review('deal-1')
        self.assertTrue(result['cached'])

    def test_changed_semantic_graph_invalidates_entire_saved_match(self):
        from types import SimpleNamespace
        from app.services.semantic_assessment import ENGINE_VERSION
        with patch('app.services.compliance_agent.db_connection') as db, \
             patch('app.services.semantic_matching.load_matcher',return_value=SimpleNamespace(fingerprint='new')):
            db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'review_id':1,'created_at':'today',
                'review':{'assessment_scope':'current-semantic-graph','knowledge_fingerprint':'old','engine_version':ENGINE_VERSION}}
            self.assertIsNone(latest_stored_compliance_review('deal-1'))
