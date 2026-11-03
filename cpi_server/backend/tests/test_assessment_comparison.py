import unittest
from copy import deepcopy

from app.services.assessment_comparison import comparison_definition, refresh_finding_comparisons


class AssessmentComparisonTests(unittest.TestCase):
    def test_restores_explicit_directions_for_missing_operators(self):
        examples = [
            ('Is concentration no more than 25%?', 25, 'less_than_or_equal'),
            ('Is exposure at or below 10% of capital?', 10, 'less_than_or_equal'),
            ('Is the report submitted within 24 hours?', 24, 'less_than_or_equal'),
            ('The maximum of 12 months applies.', 12, 'less_than_or_equal'),
            ('The exposure must not exceed USD 50 million.', 50, 'less_than_or_equal'),
            ('Is the buffer at least 10%?', 10, 'greater_than_or_equal'),
            ('Is the haircut greater than 30%?', 30, 'greater_than'),
            ('Is exposure exceeding USD 50 million?', 50, 'greater_than'),
            ('Is liquidity below 110%?', 110, 'less_than'),
            ('Is the cash haircut equal to 0%?', 0, 'equals'),
        ]
        for text, threshold, expected in examples:
            with self.subTest(text=text):
                original = {'check_question': text, 'threshold_value': threshold, 'operator': None}
                self.assertEqual(comparison_definition(original)['operator'], expected)
                self.assertIsNone(original['operator'])

    def test_matches_the_threshold_rather_than_an_unrelated_rating_number(self):
        d = {'check_question': 'Is exposure for borrowers rated 3 or higher at or below 25%?',
             'threshold_value': 25}
        self.assertEqual(comparison_definition(d)['operator'], 'less_than_or_equal')
        self.assertIsNone(comparison_definition({'check_question': 'Is exposure above 20%?',
            'threshold_value': 25}).get('operator'))

    def test_preserves_explicit_operator_over_text_recovery(self):
        d = {'operator': 'less_than', 'check_question': 'Is exposure at or below 25%?', 'threshold_value': 25}
        self.assertEqual(comparison_definition(d)['operator'], 'less_than')

    def test_recovers_ranges_and_currency_units(self):
        for question, lower, upper, unit in [
            ('Is the haircut between 5% and 20%?', 5, 20, '%'),
            ('Is exposure between USD 1 million and USD 10 million?', 1, 10, None),
        ]:
            original = {'check_question': question, 'threshold_unit': unit}
            recovered = comparison_definition(original)
            self.assertEqual(recovered['operator'], 'between')
            self.assertEqual((recovered['lower_bound'], recovered['upper_bound']), (lower, upper))
            self.assertEqual(recovered['threshold_unit'], unit or 'USD million')

    def test_screenshot_dual_review_trigger_has_comparison_and_warning_type(self):
        original = {'rule_snapshots': [{'id': 1, 'definition': {
            'threshold_value': 30, 'threshold_unit': '%', 'operator': None,
            'check_question': 'Is the haircut greater than 30%, requiring dual review by both managers?'}}],
            'findings': [{'rule_version_id': 1, 'actual': '36.0', 'observed_value': 36,
                'result': 'Unable to Assess', 'actual_sources': ['SYNTHETIC'],
                'threshold_comparison': {'condition_met': None}}]}
        unchanged = deepcopy(original)
        finding = refresh_finding_comparisons(original)['findings'][0]
        self.assertEqual(finding['operator'], 'greater_than')
        self.assertTrue(finding['threshold_comparison']['condition_met'])
        self.assertEqual(finding['threshold_type'], 'WARNING_TRIGGER')
        self.assertEqual(finding['expected_condition'], '> 30 %')
        self.assertEqual(original, unchanged)
        original['findings'][0]['observed_value'] = 30
        self.assertFalse(refresh_finding_comparisons(original)['findings'][0]['threshold_comparison']['condition_met'])

    def test_ambiguous_threshold_keeps_comparison_unknown(self):
        review = {'rule_snapshots': [{'id': 1, 'definition': {'threshold_value': 30}}],
            'findings': [{'rule_version_id': 1, 'observed_value': 36, 'actual_sources': ['SYNTHETIC']}]}
        self.assertIsNone(refresh_finding_comparisons(review)['findings'][0]['threshold_comparison']['condition_met'])


if __name__ == '__main__':
    unittest.main()
