import unittest
from unittest.mock import patch
from datetime import date
from app.services.policy_scope import policy_first_applicability

class PolicyFirstTests(unittest.TestCase):
    def test_only_rules_of_confirmed_applicable_policies_reach_rule_checks(self):
        def decision(pid,outcome):
            return {'candidate_id':str(pid),'candidate_type':'Policy','applicability':outcome,
                    'reason':'Documented scope','evaluated_attributes':{},'missing_information':[]}
        policies=[decision(1,'Applicable'),decision(2,'Not Applicable'),decision(3,'Unable to Determine')]
        rules=[{'id':pid,'policy_id':pid,'effective_from':'2020-01-01',
                'definition':{'applicability_conditions':None}} for pid in (1,2,3)]
        with patch('app.services.policy_scope.policy_decisions',return_value=policies):
            report=policy_first_applicability({'facility':'Term Loan'},rules,'In Review',date(2026,10,14))
        checked=[d for d in report['decisions'] if d['candidate_type']=='Rule']
        self.assertEqual([d['candidate_id'] for d in checked],['1'])
        self.assertEqual(report['decisions'][:3],policies)
        self.assertEqual(report['policy_mappings'],[{'policy_id':1,'policy_name':'',
            'reason':'Documented scope','rule_count':1,'rule_version_ids':[1]}])

    def test_rule_mismatch_does_not_change_policy_scope_result(self):
        policy={'candidate_id':'1','candidate_type':'Policy','applicability':'Applicable',
                'reason':'Documented scope','evaluated_attributes':{},'missing_information':[]}
        rule={'id':1,'policy_id':1,'effective_from':'2020-01-01','definition':{
            'applicability_conditions':{'field':'facility','operator':'equals','value':'Home Loan'}}}
        with patch('app.services.policy_scope.policy_decisions',return_value=[policy]):
            report=policy_first_applicability({'facility':'Term Loan'},[rule],'In Review',date(2026,10,14))
        self.assertEqual(report['decisions'][0]['applicability'],'Applicable')
        self.assertEqual(report['decisions'][1]['applicability'],'Not Applicable')
        self.assertEqual(report['policy_mappings'][0]['rule_count'],0)

    def test_unresolved_mapping_does_not_override_confirmed_facility_exclusion(self):
        from app.agents.credit_request_policy_applicability import evaluate_conditions
        result,_,_=evaluate_conditions({'applicability_unresolved':True,
            'applicability_conditions':{'field':'facility','operator':'equals','value':'Credit Card'}},
            {'facility':'Term Loan'})
        self.assertIs(result,False)

class SourceReferenceTests(unittest.TestCase):
    def test_provider_failures_return_safe_actionable_errors(self):
        import httpx
        from fastapi import HTTPException
        from mistralai.client.errors import SDKError
        from unittest.mock import MagicMock
        from app.services.policy_scope import policy_decisions
        for provider_status, expected_status in ((402, 402), (429, 429), (401, 502), (500, 502)):
            with self.subTest(provider_status=provider_status):
                connection = MagicMock()
                connection.__enter__.return_value.execute.return_value.fetchall.return_value = [
                    {'policy_id': 1, 'title': 'Term loans', 'summary': 'Applies to term loans.',
                     'effective_date': date(2020, 1, 1), 'scope_excerpts': []}]
                client = MagicMock()
                client.__enter__.return_value.chat.parse.side_effect = SDKError(
                    'API error occurred', httpx.Response(provider_status, text='private provider details'))
                with patch('app.services.policy_scope.shared_policy_connection', return_value=connection), \
                     patch('app.services.policy_scope.Mistral', return_value=client), \
                     patch('app.services.policy_scope.MISTRAL_API_KEY', 'test'):
                    with self.assertRaises(HTTPException) as caught:
                        policy_decisions({'facility': 'Term Loan'}, [{'policy_id': 1}], date(2026, 10, 24))
                self.assertEqual(caught.exception.status_code, expected_status)
                self.assertNotIn('private provider details', caught.exception.detail)
                if provider_status == 402:
                    self.assertIn('spending limit', caught.exception.detail)
                    self.assertIn('administrator', caught.exception.detail)
                client.__enter__.return_value.chat.parse.assert_called_once()

    def test_valid_source_reference_retains_policy_match(self):
        from unittest.mock import MagicMock
        from app.services.policy_scope import policy_decisions,PolicyScopeBatch,PolicyScopeDecision
        connection=MagicMock()
        connection.__enter__.return_value.execute.return_value.fetchall.return_value=[
            {'policy_id':1,'title':'Term loans','summary':'Applies to all term loans.',
             'effective_date':date(2020,1,1),'scope_excerpts':[]}]
        client=MagicMock()
        client.__enter__.return_value.chat.parse.return_value.choices[0].message.parsed=PolicyScopeBatch(
            decisions=[PolicyScopeDecision(policy_id=1,applicability='Applicable',reason='Facility matches scope',
                        source_reference=0,evaluated_attributes={'facility':'Term Loan'},missing_information=[])])
        with patch('app.services.policy_scope.shared_policy_connection',return_value=connection), \
             patch('app.services.policy_scope.Mistral',return_value=client), \
             patch('app.services.policy_scope.MISTRAL_API_KEY','test'):
            report=policy_decisions({'facility':'Term Loan'},[{'policy_id':1}],date(2026,10,14))
        self.assertEqual(report[0]['applicability'],'Applicable')
        self.assertIn('Source passage 1',report[0]['reason'])
