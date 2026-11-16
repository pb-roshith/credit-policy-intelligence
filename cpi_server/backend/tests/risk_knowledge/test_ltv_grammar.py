import copy
import unittest
from unittest.mock import patch
from app.risk_knowledge.policy_grammar import parse_requirements,classify_non_rule
from app.risk_knowledge.policy_representation import build_representation,compile_graph,seal,coverage_summary
from app.services.rule_engine import execute_rule

INVESTMENT='Investment properties are subject to a stricter LTV ceiling of 70% for conventional loans and 75% for government-insured loans.'
SECONDARY='For secondary or vacation homes, the maximum LTV is reduced to 70% for conventional loans and 80% for government-insured loans.'
AUTO='Auto loans are subject to a maximum LTV of 120% for new vehicles and 100% for used vehicles.'


def build(text):
    return build_representation({'policy_id':6,'title':'LTV Ceilings'},{'id':21,'version':'1'},
                                {'checksum':'source'},[{'id':127,'source_excerpt':text}])


class LTVGrammarTests(unittest.TestCase):
    def test_investment_branch_thresholds_match_only_their_own_programme(self):
        rep=build(INVESTMENT);rules=compile_graph(rep,rep['source_clauses'])
        self.assertEqual(len(rules),2)
        self.assertEqual(coverage_summary(rep)['VALIDATED'],1)
        outcomes=[]
        for program in ('Conventional','Government-Insured'):
            request={'property_type':'Investment Property','loan_program':program,'ltv':72}
            results=[]
            for rule in rules:
                d=rule.model_dump();d['severity']='BREACH'
                results.append(execute_rule(d,request)['result'])
            outcomes.append(sorted(results))
        self.assertEqual(outcomes,[['Breach','Not Applicable'],['Not Applicable','Pass']])

    def test_shared_property_scope_is_not_lost_or_assumed(self):
        rep=build(INVESTMENT);rules=compile_graph(rep,rep['source_clauses'])
        for rule in rules:
            self.assertEqual(execute_rule(rule.model_dump(),{'property_type':'Primary Residence','loan_program':'Conventional','ltv':72})['result'],'Not Applicable')
        self.assertEqual(sorted(execute_rule(rule.model_dump(),{'loan_program':'Conventional','ltv':72})['result'] for rule in rules),['Not Applicable','Unable to Assess'])

    def test_property_alternatives_stay_grouped_with_the_loan_programme(self):
        rep=build(SECONDARY);rules=compile_graph(rep,rep['source_clauses'])
        self.assertEqual(len(rules),2)
        for property_type in ('Secondary Residence','Vacation Home'):
            results=[execute_rule(r.model_dump(),{'property_type':property_type,'loan_program':'Government-Insured','ltv':75})['result'] for r in rules]
            self.assertEqual(sorted(results),['Not Applicable','Pass'])

    def test_vehicle_branches_are_not_applied_to_other_facilities(self):
        rep=build(AUTO);rules=compile_graph(rep,rep['source_clauses'])
        for rule in rules:
            self.assertEqual(execute_rule(rule.model_dump(),{'facility':'Mortgage','vehicle_condition':'New','ltv':110})['result'],'Not Applicable')
        self.assertEqual(sorted(execute_rule(r.model_dump(),{'facility':'Auto Loan','vehicle_condition':'New','ltv':110})['result'] for r in rules),['Not Applicable','Pass'])

    def test_pdf_wrap_inside_hyphenated_programme_does_not_change_quote(self):
        quote=INVESTMENT.replace('government-insured','government-\ninsured')
        rep=build(quote);rules=compile_graph(rep,rep['source_clauses'])
        self.assertEqual(len(rules),2)
        self.assertTrue(all(r.source_excerpt==quote for r in rules))

    def test_missing_or_duplicated_branch_is_rejected_after_resealing(self):
        rep=build(INVESTMENT)
        rep['coverage'][0]['requirement_ids'].pop()
        seal(rep)
        with self.assertRaises(ValueError):compile_graph(rep,rep['source_clauses'])

    def test_qualifiers_unknown_programmes_and_example_language_do_not_get_discarded(self):
        for quote in [INVESTMENT[:-1]+', unless separately approved.',
                      INVESTMENT.replace('government-insured loans','bespoke loans'),
                      'For example, '+INVESTMENT[0].lower()+INVESTMENT[1:],
                      INVESTMENT[:-1]+', provided cash flow is stable.',
                      INVESTMENT.replace('and 75%','or 75%')]:
            with self.subTest(quote=quote):self.assertFalse(parse_requirements(quote)[0])

    def test_heterogeneous_overlapping_matrix_is_not_flattened_or_partially_extracted(self):
        quote='For mortgage loans, the maximum LTV ceiling is set at 80% for conventional loans, 90% for loans insured by a government agency, and 70% for investment properties.'
        self.assertFalse(parse_requirements(quote)[0])

    def test_old_representation_route_uses_current_semantic_evidence(self):
        from app.routers.risk_knowledge import policy_representation
        with patch('app.routers.risk_knowledge.semantic_policy_representation',return_value={'current':True}) as current:
            self.assertEqual(policy_representation(6,'old-span'),{'current':True})
        current.assert_called_once_with(6)


class SourceClassificationTests(unittest.TestCase):
    def test_numbering_and_complete_page_furniture_are_structure(self):
        for quote in ['1. 1.','10. 10.','CP-Retail-v3.1 \u00a73.2 | Synthetic policy data\nPage 7',
                      'CP-Retail-v3.1 \u00a73.2 | Synthetic policy data\nPage 1\n3.2 LTV Ceilings\nCP-Retail-v3.1 \u00a73.2 \u00b7 Effective 2026-09-10']:
            with self.subTest(quote=quote):self.assertEqual(classify_non_rule(quote)['category'],'DOCUMENT_STRUCTURE')

    def test_screenshot_purpose_and_rationale_are_retained_as_context(self):
        purpose='Purpose The purpose of this clause, 3.2 LTV Ceilings, under the parent policy CP-Retail-v3.1, is to establish clear, consistent, and risk-based Loan-to-Value (LTV) ceilings for all retail lending products offered by the bank.'
        background='This clause ensures that the bank maintains a prudent balance between risk exposure and customer accessibility, aligning with regulatory requirements and internal risk appetite frameworks.'
        self.assertEqual(classify_non_rule(purpose)['category'],'PURPOSE')
        self.assertEqual(classify_non_rule(background)['category'],'BACKGROUND')
        rep=build(purpose+'\n'+background)
        self.assertEqual(coverage_summary(rep)['NON_RULE'],2)
        self.assertEqual(compile_graph(rep,rep['source_clauses']),[])

    def test_heading_or_purpose_does_not_hide_an_obligation_limit_or_scope_exclusion(self):
        for quote in ['1. Borrowers must submit audited financial statements',
                      'Purpose The purpose of this policy is to require an appraisal.',
                      'The purpose of this clause is to limit LTV to 70%.',
                      'This clause ensures collateral is valued by an independent appraiser.',
                      'This clause ensures that the bank maintains a prudent balance between access and risk; LTV must not exceed 80%.',
                      'CP-Retail-v3.1 \u00a73.2 | Synthetic policy data\nLTV shall not exceed 80%.',
                      'This policy does not apply to unsecured loans.',
                      'All exceptions must be documented in the LOS.']:
            with self.subTest(quote=quote):self.assertIsNone(classify_non_rule(quote))


if __name__=='__main__':unittest.main()
