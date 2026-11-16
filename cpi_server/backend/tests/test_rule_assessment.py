import unittest
from app.services.rule_assessment import evaluate

class RuleEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.rule = {"stage_applicable":"All", "metric":"requested_amount", "operator":"<=", "threshold":100, "severity":"BREACH", "applicability":{}}
    def test_boundary_pass_and_breach(self):
        self.assertEqual(evaluate(self.rule,{"requested_amount":100})[1],"PASS")
        self.assertEqual(evaluate(self.rule,{"requested_amount":101})[1],"BREACH")
    def test_missing_metric_warns(self):
        self.assertEqual(evaluate(self.rule,{})[1],"WARNING")
    def test_not_applicable(self):
        self.rule["applicability"] = {"facility":"Term Loan"}
        self.assertEqual(evaluate(self.rule,{"facility":"Overdraft"})[:2],("Not applicable",None))
    def test_missing_applicability_warns(self):
        self.rule["applicability"] = {"facility":"Term Loan"}
        self.assertEqual(evaluate(self.rule,{})[1],"WARNING")
    def test_stage(self):
        self.rule["stage_applicable"] = "Under Review"
        self.assertEqual(evaluate(self.rule,{"status":"Draft"})[0],"Not applicable")
    def test_nonfinite_warns(self):
        self.assertEqual(evaluate(self.rule,{"requested_amount":"NaN"})[1],"WARNING")
    def test_invalid_numeric_warns(self):
        self.assertEqual(evaluate(self.rule,{"requested_amount":"unknown"})[1],"WARNING")

class UnavailableRulesTests(unittest.TestCase):
    def test_no_effective_rules_stops_assessment_without_requiring_activation(self):
        from unittest.mock import patch
        from fastapi import HTTPException
        from app.services.rule_assessment import run_rule_assessment
        with patch('app.services.rule_assessment.assessment_request_context',return_value=('CR-1',{})), \
             patch('app.services.rule_assessment.active_rule_candidates',return_value=[]), \
             patch('app.services.rule_engine.execute_rule') as execute:
            with self.assertRaises(HTTPException) as raised:
                run_rule_assessment('CR-1','test')
        self.assertEqual(raised.exception.status_code,409)
        self.assertIn('no activation is required',raised.exception.detail)
        execute.assert_not_called()


class ApplicableOnlyAssessmentTests(unittest.TestCase):
    def test_unknown_and_inapplicable_rules_are_never_compared(self):
        from unittest.mock import patch, MagicMock
        from app.services.rule_assessment import run_rule_assessment
        rules=[{'id':1,'effective_from':'2020-01-01','definition':{'applicability_conditions':{'field':'facility','operator':'equals','value':'Home Loan'}}},
               {'id':2,'effective_from':'2020-01-01','definition':{'applicability_conditions':{'field':'segment','operator':'equals','value':'Retail'}}}]
        connection=MagicMock()
        connection.__enter__.return_value.execute.return_value.fetchall.return_value=[]
        with patch('app.services.rule_assessment.assessment_request_context',return_value=('CR-1',{'facility':'Business Loan','status':'In Review','evidence':[]})), \
             patch('app.services.rule_assessment.active_rule_candidates',return_value=rules), \
             patch('app.services.rule_assessment.shared_policy_connection',return_value=connection), \
             patch('app.services.rule_assessment.run_db_transaction',return_value={'review_id':1}), \
             patch('app.services.rule_explanation.explain_findings'), \
             patch('app.services.policy_scope.policy_first_applicability',return_value={'decisions':[{'candidate_type':'Rule','candidate_id':'2','applicability':'Unable to Determine'}],'policy_mappings':[]}), \
             patch('app.services.rule_engine.execute_rule') as execute:
            result=run_rule_assessment('CR-1','test')
        execute.assert_not_called()
        self.assertEqual(result['findings'],[])
        self.assertIsNone(result['overall_score'])
        self.assertEqual(result['assessment_scope'],'policy-first-applicable-only')
        self.assertEqual(result['compliance_status'],'Incomplete assessment')

if __name__ == "__main__":
    unittest.main()
