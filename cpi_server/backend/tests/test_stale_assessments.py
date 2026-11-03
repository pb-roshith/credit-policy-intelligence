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

    def test_retained_rules_keep_saved_assessment(self):
        review = self.load_review([10, 11])
        self.assertEqual(review['review_id'], 7)
        self.assertTrue(review['cached'])
