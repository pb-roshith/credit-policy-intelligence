import unittest
from copy import deepcopy
from datetime import date
from unittest.mock import MagicMock, patch

from app.manufacture_data.assessment_data import (sample_financials,
    manufacture_assessment_inputs, supplement_actual_resolution, manufacture_observed_actual)
from app.services.rule_engine import execute_rule
from app.services.credit_data import resolve_actual, fact


AS_OF = date(2026, 11, 2)


def rule(rule_id=1, method='direct', field='custom_metric', threshold=10, unit='x', **logic):
    return {'id': rule_id, 'policy_id': 1, 'policy_version_id': 1, 'policy_version': '1',
        'title': 'Demo policy', 'policy_type': 'Credit', 'rule_entity_id': rule_id,
        'version': 1, 'rule_code': f'R-{rule_id}', 'clause_id': 1, 'document_id': 1,
        'file_name': 'policy.pdf', 'checksum': 'abc', 'section_heading': 'Limits',
        'clause_number': '1', 'page_number': 1,
        'definition': {'rule_name': 'Demo metric', 'source_excerpt': 'Approved limit',
            'operator': 'less_than_or_equal', 'threshold_value': threshold,
            'threshold_unit': unit, 'severity': 'BREACH', 'input_data_fields': [],
            'evidence_requirements': [], 'applicability_conditions': None,
            'calculation_logic': {'method': method, 'field': field, **logic}}}


class AssessmentManufacturingTests(unittest.TestCase):
    def test_manual_mapping_gets_actual_in_threshold_units_and_comparison(self):
        r = rule(method='manual', threshold=50, unit='USD million')
        r['definition']['severity'] = None
        r['definition']['evidence_requirements'] = [{'key': 'application', 'type': 'human'}]
        original = execute_rule(r['definition'], {}, AS_OF)
        result, source = manufacture_observed_actual('CR-1', r, original, AS_OF)
        self.assertIsNone(original['observed_value'])
        self.assertIn(result['observed_value'], (40, 60))
        self.assertEqual(result['threshold_comparison']['condition_met'], result['observed_value'] <= 50)
        self.assertEqual(result['result'], 'Manual Review Required')
        self.assertEqual(source['unit'], 'USD million')
        self.assertEqual(source['provenance']['source_type'], 'SYNTHETIC')
        repeated, repeated_source = manufacture_observed_actual('CR-1', r, original, AS_OF)
        self.assertEqual(result, repeated)
        self.assertEqual(source['value'], repeated_source['value'])

    def test_manual_mapping_without_any_input_fields_still_gets_actual(self):
        r = rule(method='manual', threshold=180, unit='days')
        r['definition']['operator'] = None
        original = execute_rule(r['definition'], {}, AS_OF)
        result, source = manufacture_observed_actual('CR-1', r, original, AS_OF)
        self.assertIsNotNone(result['observed_value'])
        self.assertIsNotNone(source)
        self.assertIsNone(result['threshold_comparison']['condition_met'])
        self.assertEqual(result['result'], 'Manual Review Required')

    def test_fallback_keeps_existing_calculated_actual(self):
        r = rule()
        original = execute_rule(r['definition'], {'custom_metric': 42}, AS_OF)
        result, source = manufacture_observed_actual('CR-1', r, original, AS_OF)
        self.assertEqual(result, original)
        self.assertIsNone(source)

    def test_fallback_range_actual_comparison(self):
        r = rule(method='manual')
        r['definition'].update(operator='between', lower_bound=5, upper_bound=20)
        for request in ('CR-1', 'CR-2'):
            original = execute_rule(r['definition'], {}, AS_OF)
            result, _ = manufacture_observed_actual(request, r, original, AS_OF)
            actual = result['observed_value']
            self.assertEqual(result['threshold_comparison']['condition_met'], 5 <= actual <= 20)

    def test_run_manual_mapping_saves_displayed_actual_and_synthetic_provenance(self):
        from app.services.rule_assessment import run_rule_assessment
        r = rule(method='manual', threshold=50, unit='USD million')
        r['definition']['severity'] = None
        record = {'request_id': 'CR-1', 'entities': {}, 'evidence': []}
        connection = MagicMock()
        connection.__enter__.return_value.execute.return_value.fetchall.return_value = []
        report = {'decisions': [{'candidate_type': 'Rule', 'candidate_id': '1', 'applicability': 'Applicable'}]}
        with patch('app.services.rule_assessment.assessment_request_context', return_value=('CR-1', {'evidence': [], '_canonical_record': record})), \
             patch('app.services.rule_assessment.active_rule_candidates', return_value=[r]), \
             patch('app.services.policy_scope.policy_first_applicability', return_value=report), \
             patch('app.services.rule_assessment.shared_policy_connection', return_value=connection), \
             patch('app.services.rule_assessment.run_db_transaction', return_value={'review_id': 8}):
            review = run_rule_assessment('CR-1', 'test')
        finding = review['findings'][0]
        self.assertNotEqual(finding['actual'], 'Unavailable')
        self.assertEqual(finding['actual_data_resolution']['actual_value'], finding['observed_value'])
        self.assertEqual(finding['actual_data_resolution']['actual_provenance']['source_type'], 'SYNTHETIC')
        self.assertIn('SYNTHETIC', finding['actual_sources'])
        self.assertEqual(finding['threshold_comparison']['actual'], finding['observed_value'])
        self.assertTrue(review['demonstration_data_used'])

    def test_direct_inputs_are_stable_shared_and_leave_request_unchanged(self):
        proposal = {'status': 'In Review', 'evidence': []}
        original = deepcopy(proposal)
        rules = [rule(), rule(2, threshold=20)]
        data, generated = manufacture_assessment_inputs('CR-1', proposal, rules, AS_OF)
        self.assertEqual(proposal, original)
        self.assertEqual(generated['custom_metric'], data['custom_metric'])
        self.assertEqual((data, generated), manufacture_assessment_inputs('CR-1', proposal, rules, AS_OF))
        for r in rules:
            outcome = execute_rule(r['definition'], data, AS_OF)
            self.assertEqual(outcome['observed_value'], data['custom_metric'])
            self.assertIn(outcome['result'], ('Pass', 'Breach'))

    def test_existing_actual_and_policy_definition_are_preserved(self):
        r = rule()
        original = deepcopy(r)
        data, generated = manufacture_assessment_inputs('CR-1', {'custom_metric': 42}, [r], AS_OF)
        self.assertEqual(data['custom_metric'], 42)
        self.assertEqual(generated, {})
        self.assertEqual(r, original)
        self.assertEqual(execute_rule(r['definition'], data, AS_OF)['result'], 'Breach')

    def test_supported_calculations_receive_evaluable_inputs(self):
        rules = [rule(1, method='ratio', numerator='debt', denominator='earnings'),
                 rule(2, method='percentage', numerator='balance', denominator='portfolio', unit='%'),
                 rule(3, method='date_age', field='statement_date', unit='days'),
                 rule(4, field='amount', threshold=2, unit='million USD'),
                 rule(5, field='nested.metric')]
        data, generated = manufacture_assessment_inputs('CR-1', {'currency': 'USD'}, rules, AS_OF)
        self.assertGreater(data['earnings'], 0)
        self.assertGreater(data['amount'], 1000000)
        self.assertIn('nested.metric', generated)
        for r in rules:
            with self.subTest(method=r['definition']['calculation_logic']):
                outcome = execute_rule(r['definition'], data, AS_OF)
                self.assertIsNotNone(outcome['observed_value'])
                self.assertIn(outcome['result'], ('Pass', 'Breach'))

    def test_categorical_range_and_boolean_rules(self):
        categorical = rule(1, field='rating', threshold=['BBB', 'A'], unit='rating')
        categorical['definition']['operator'] = 'in_list'
        bounded = rule(2, field='bounded')
        bounded['definition'].update(operator='between', lower_bound=5, upper_bound=20)
        boolean = rule(3, field='verified', threshold=True, unit='boolean')
        boolean['definition']['operator'] = 'equals'
        for r in (categorical, bounded, boolean):
            data, _ = manufacture_assessment_inputs('CR-1', {}, [r], AS_OF)
            self.assertIn(execute_rule(r['definition'], data, AS_OF)['result'], ('Pass', 'Breach'))

    def test_evidence_is_labelled_and_human_judgment_stays_manual(self):
        r = rule()
        r['definition']['evidence_requirements'] = [{'key': 'report', 'type': 'document'}]
        data, _ = manufacture_assessment_inputs('CR-1', {}, [r], AS_OF)
        self.assertEqual(data['evidence'][0]['source_type'], 'SYNTHETIC')
        self.assertIn(execute_rule(r['definition'], data, AS_OF)['result'], ('Pass', 'Breach'))
        r['definition']['evidence_requirements'].append({'key': 'judgment', 'type': 'human'})
        self.assertEqual(execute_rule(r['definition'], data, AS_OF)['result'], 'Manual Review Required')

    def test_missing_scope_attributes_are_never_manufactured(self):
        r = rule()
        r['definition'].update(input_data_fields=['segment'],
            applicability_conditions={'field': 'segment', 'operator': 'equals', 'value': 'Retail'})
        data, generated = manufacture_assessment_inputs('CR-1', {}, [r], AS_OF)
        self.assertNotIn('segment', generated)
        self.assertNotIn('segment', data)
        self.assertEqual(execute_rule(r['definition'], data, AS_OF)['result'], 'Unable to Assess')

    def test_canonical_missing_inputs_get_synthetic_lineage(self):
        r = rule()
        record = {'request_id': 'CR-1', 'entities': {}, 'evidence': []}
        resolution = resolve_actual(r, record, as_of=AS_OF)
        data, generated = manufacture_assessment_inputs('CR-1', {}, [r], AS_OF)
        result = supplement_actual_resolution(r, resolution, data, generated, AS_OF)
        self.assertEqual(resolution['resolution_status'], 'MISSING')
        self.assertEqual(result['resolution_status'], 'COMPLETE')
        self.assertEqual(result['provenance'][0]['source_type'], 'SYNTHETIC')
        self.assertEqual(result['actual_provenance']['inputs'][0]['verification_status'], 'MANUFACTURED')
        self.assertIn(result['evaluation']['result'], ('Pass', 'Breach'))

    def test_canonical_real_actual_is_not_replaced_by_generated_input(self):
        r = rule()
        record = {'request_id': 'CR-1', 'evidence': [], 'entities': {'requirement': [
            {'entity_id': 'borrower', 'attributes': {'custom_metric': fact('CR-1',
                'requirement.custom_metric', 42, unit='x', source_type='MANUAL', as_of=AS_OF.isoformat())}}]}}
        resolution = resolve_actual(r, record, as_of=AS_OF)
        data, generated = manufacture_assessment_inputs('CR-1', {}, [r], AS_OF)
        result = supplement_actual_resolution(r, resolution, data, generated, AS_OF)
        self.assertEqual(result['actual_value'], 42)
        self.assertEqual(result['provenance'][0]['source_type'], 'MANUAL')

    def test_conflicting_canonical_data_is_not_replaced(self):
        r = rule()
        record = {'request_id': 'CR-1', 'entities': {}, 'evidence': []}
        resolution = resolve_actual(r, record, as_of=AS_OF)
        resolution['resolution_status'] = 'CONFLICTING'
        resolution['evaluation']['result'] = 'Manual Review Required'
        data, generated = manufacture_assessment_inputs('CR-1', {}, [r], AS_OF)
        result = supplement_actual_resolution(r, resolution, data, generated, AS_OF)
        self.assertEqual(result, resolution)

    def test_invalid_existing_date_input_does_not_crash_manufacturing(self):
        r = rule(method='date_age', field='statement_date', unit='days', as_of_field='review_date')
        data, _ = manufacture_assessment_inputs('CR-1', {'review_date': 'invalid'}, [r], AS_OF)
        self.assertEqual(execute_rule(r['definition'], data, AS_OF)['result'], 'Unable to Assess')

    def test_run_assessment_manufactures_only_applicable_rules_and_saves_snapshot(self):
        from app.services.rule_assessment import run_rule_assessment
        selected, excluded = rule(), rule(2, field='excluded_metric')
        connection = MagicMock()
        connection.__enter__.return_value.execute.return_value.fetchall.return_value = []
        report = {'decisions': [
            {'candidate_type': 'Rule', 'candidate_id': '1', 'applicability': 'Applicable'},
            {'candidate_type': 'Rule', 'candidate_id': '2', 'applicability': 'Not Applicable'}]}
        with patch('app.services.rule_assessment.assessment_request_context', return_value=('CR-1', {'evidence': []})), \
             patch('app.services.rule_assessment.active_rule_candidates', return_value=[selected, excluded]), \
             patch('app.services.policy_scope.policy_first_applicability', return_value=report), \
             patch('app.services.rule_assessment.shared_policy_connection', return_value=connection), \
             patch('app.services.rule_assessment.run_db_transaction', return_value={'review_id': 7}) as persist:
            result = run_rule_assessment('CR-1', 'test')
        persist.assert_called_once()
        self.assertEqual(result['review_id'], 7)
        self.assertEqual(len(result['findings']), 1)
        finding = result['findings'][0]
        self.assertEqual(finding['observed_value'], result['manufactured_inputs']['custom_metric'])
        self.assertEqual(finding['actual_sources'], ['SYNTHETIC'])
        self.assertTrue(result['demonstration_data_used'])
        self.assertNotIn('excluded_metric', result['manufactured_inputs'])
        self.assertIn(finding['result'], ('Pass', 'Breach'))


class SampleFinancialTests(unittest.TestCase):
    def test_financial_ratios_correspond_to_stored_underlying_values(self):
        data=sample_financials(10_000_000,20_000_000)
        self.assertEqual(data['total_debt'],30_000_000)
        self.assertAlmostEqual(data['total_debt']/data['ebitda'],data['leverage_ratio'],places=6)
        self.assertAlmostEqual(data['net_operating_income']/data['annual_debt_service'],data['dscr'],places=6)
        self.assertAlmostEqual(100*data['total_debt']/data['collateral_value'],data['ltv'],places=6)
