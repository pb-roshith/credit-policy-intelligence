import unittest
from unittest.mock import patch
from app.services.rule_expectation import expected_condition

class ExpectedConditionTests(unittest.TestCase):
    def test_numeric_zero_and_boolean_are_preserved(self):
        self.assertEqual(expected_condition({'operator':'less_than_or_equal','threshold_value':0,'threshold_unit':'%'}),'<= 0 %')
        self.assertEqual(expected_condition({'operator':'equals','threshold_value':True}),'= Yes')
    def test_presence_and_bounds(self):
        self.assertEqual(expected_condition({'operator':'exists'}),'Must be present')
        self.assertEqual(expected_condition({'operator':'between','lower_bound':1,'upper_bound':5}),'Between 1 and 5')
    def test_missing_numeric_limit_uses_source_check_without_inventing_value(self):
        self.assertEqual(expected_condition({'check_question':'Is the RCO approval present?'}),'Is the RCO approval present?')
        self.assertIn('correction required',expected_condition({}))

class FreshAssessmentTests(unittest.TestCase):
    def test_run_always_recalculates_even_when_recalculate_is_false(self):
        from app.routers.compliance import run_compliance_review
        from app.schemas import ComplianceReviewRequest
        with patch('app.routers.compliance.latest_stored_compliance_review') as saved, \
             patch('app.services.semantic_assessment.run_rule_assessment',return_value={'findings':[]}) as run:
            result=run_compliance_review(ComplianceReviewRequest(credit_request_number='CR-1',recalculate=False),{'user_id':'test'})
        saved.assert_not_called()
        run.assert_called_once()
        self.assertFalse(result['cached'])
