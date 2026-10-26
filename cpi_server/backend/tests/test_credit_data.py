import copy
import unittest
from datetime import date
from app.services.credit_data import (fact, synthetic_record, resolve_actual, derive_registry,
                                      read_fact, normalize_unit, tenor_months, validate_record, coverage_report)

AS_OF = date(2026, 10, 14)


def rule(field='revolving_credit_tenor', threshold=5, unit='years', operator='less_than_or_equal', severity='BREACH', method='direct', **logic):
    return {'id': 1, 'policy_id': 10, 'definition': {
        'rule_name': 'Governed test rule', 'operator': operator, 'threshold_value': threshold,
        'threshold_unit': unit, 'severity': severity, 'input_data_fields': [field],
        'applicable_stage': None, 'applicability_conditions': None, 'evidence_requirements': [],
        'calculation_logic': {'method': method, 'field': field, **logic}}}


def proposal():
    return {'credit_request_number': 'CR-TEST', 'borrower_name': 'Synthetic Company',
            'requested_amount': 10000000, 'exposure': 20000000, 'facility': 'Revolver',
            'recommended_tenor_years': 3, 'rating': 'BBB', 'status': 'In Review'}


class CanonicalDataTests(unittest.TestCase):
    def record(self, scenario='compliant', rules=None):
        return synthetic_record(proposal(), rules or [rule()], scenario, AS_OF)

    def test_tenor_comparison_end_to_end(self):
        record = self.record(); resolution = resolve_actual(rule(), record, as_of=AS_OF)
        self.assertEqual(resolution['evaluation']['result'], 'Pass')
        self.assertEqual(resolution['actual_value'], 4)
        self.assertEqual(resolution['unit'], 'years')
        self.assertEqual(resolution['provenance'][0]['source_type'], 'DERIVED')
        self.assertEqual(resolution['provenance'][0]['inputs'][0]['source_type'], 'SYNTHETIC')

    def test_breach_and_warning(self):
        record = self.record('breach')
        self.assertEqual(resolve_actual(rule(), record, as_of=AS_OF)['evaluation']['result'], 'Breach')
        self.assertEqual(resolve_actual(rule(severity='WARNING'), record, as_of=AS_OF)['evaluation']['result'], 'Warning')

    def test_boundary_operator(self):
        record = self.record('boundary')
        self.assertEqual(resolve_actual(rule(), record, as_of=AS_OF)['evaluation']['result'], 'Pass')
        self.assertEqual(resolve_actual(rule(operator='less_than'), record, as_of=AS_OF)['evaluation']['result'], 'Breach')

    def test_units(self):
        self.assertEqual(normalize_unit(60, 'months', 'years'), 5)
        self.assertEqual(normalize_unit(.8, 'x', '%'), 80)
        self.assertEqual(normalize_unit(5000000, 'USD', 'million USD'), 5)
        with self.assertRaises(ValueError): normalize_unit(10, 'USD', 'INR')
        self.assertEqual(normalize_unit(100,'bps','%'),1)

    def test_date_age_calendar_units(self):
        from app.services.rule_engine import execute_rule
        d=rule('start_date',36,'months',method='date_age')['definition']
        self.assertEqual(execute_rule(d,{'start_date':'2023-10-14'},AS_OF)['observed_value'],36)
        d['threshold_unit']='business days'
        self.assertEqual(execute_rule(d,{'start_date':'2023-10-14'},AS_OF)['result'],'Unable to Assess')

    def test_derived_tenor(self):
        self.assertEqual(tenor_months('2026-01-01','2029-01-01'), 36)
        self.assertEqual(tenor_months('2026-01-31','2026-02-28'), 1)
        self.assertGreater(tenor_months('2026-01-01','2026-02-15'), 1)
        with self.assertRaises(ValueError): tenor_months('2027-01-01','2026-01-01')

    def test_leverage_calculation(self):
        r = rule('total_debt', 4.5, 'x', method='ratio', numerator='total_debt', denominator='ebitda')
        record = self.record(rules=[r])
        result = resolve_actual(r, record, as_of=AS_OF)
        self.assertAlmostEqual(result['actual_value'], 3.6)
        self.assertEqual(result['evaluation']['result'], 'Pass')

    def test_collateral_ratios(self):
        r = rule('loan_amount', 80, '%', method='ratio', numerator='loan_amount', denominator='collateral_value')
        record = self.record(rules=[r]); result = resolve_actual(r, record, as_of=AS_OF)
        self.assertAlmostEqual(result['actual_value'], 64)
        self.assertEqual(result['evaluation']['result'], 'Pass')
        self.assertAlmostEqual(read_fact(record,'metric.ltv_percent')['value'], 64)
        self.assertAlmostEqual(read_fact(record,'collateral.eligible_value')['value'], 12500000)

    def test_missing_data_never_generated(self):
        record = self.record('missing'); before = copy.deepcopy(record)
        result = resolve_actual(rule(),record,as_of=AS_OF)
        self.assertEqual(result['evaluation']['result'],'Unable to Assess')
        self.assertIn('facility.tenor_months',result['missing_fields'])
        self.assertEqual(record,before)

    def test_conflicting_data(self):
        result = resolve_actual(rule(),self.record('conflicting'),as_of=AS_OF)
        self.assertEqual(result['resolution_status'],'CONFLICTING')
        self.assertEqual(result['evaluation']['result'],'Manual Review Required')

    def test_multi_facility_evaluates_all_and_allows_selection(self):
        record = self.record(); other = copy.deepcopy(record['entities']['facility'][0]); other['entity_id']='second'
        record['entities']['facility'].append(other)
        aggregate=resolve_actual(rule(),record,as_of=AS_OF)
        self.assertEqual(aggregate['evaluation']['result'],'Pass')
        self.assertEqual(len(aggregate['instances']),2)
        self.assertEqual(resolve_actual(rule(),record,entity_id='second',as_of=AS_OF)['evaluation']['result'],'Pass')
        other['attributes']['maturity_date']['value']='2036-10-01'
        self.assertEqual(resolve_actual(rule(),record,as_of=AS_OF)['evaluation']['result'],'Breach')

    def test_multiple_reporting_periods(self):
        r = rule('total_debt',4.5,'x',method='ratio',numerator='total_debt',denominator='ebitda')
        record = self.record(rules=[r]); financial = record['entities']['financial'][0]; financial['period_end']='2025-12-31'
        other=copy.deepcopy(financial); other['period_end']='2024-12-31'; record['entities']['financial'].append(other)
        self.assertEqual(resolve_actual(r,record,as_of=AS_OF)['evaluation']['result'],'Unable to Assess')
        self.assertEqual(resolve_actual(r,record,period='2025-12-31',as_of=AS_OF)['evaluation']['result'],'Pass')

    def test_provenance_synthetic_identity(self):
        record=self.record()
        for entities in record['entities'].values():
            for entity in entities:
                for item in entity['attributes'].values():
                    self.assertEqual(item['provenance']['source_type'],'SYNTHETIC')
                    self.assertEqual(item['provenance']['verification_status'],'MANUFACTURED')
        record['entities']['facility'][0]['attributes']['requested_amount']['provenance']['value']=1
        with self.assertRaises(ValueError): validate_record(record)

    def test_registry_aliases_and_unresolved_fields(self):
        r=rule(); r['definition']['input_data_fields']=['term_loan_tenor','revolving_credit_tenor','opaque_governance_input']
        attributes,mappings=derive_registry([r]); registry={a['canonical_field_name']:a for a in attributes}
        self.assertIn('term_loan_tenor',registry['facility.tenor_months']['aliases'])
        self.assertIn('revolving_credit_tenor',registry['facility.tenor_months']['aliases'])
        self.assertEqual(registry['requirement.opaque_governance_input']['metadata_status'],'REQUIRES_DEFINITION')
        self.assertEqual(mappings[0]['field_map']['term_loan_tenor'],'facility.tenor_months')

    def test_snapshot_does_not_follow_future_mutation(self):
        record=self.record(); snapshot=resolve_actual(rule(),record,as_of=AS_OF)
        record['entities']['facility'][0]['attributes']['start_date']['value']='2020-01-01'
        self.assertEqual(snapshot['actual_value'],4)
        self.assertEqual(snapshot['provenance'][0]['inputs'][0]['value'],'2026-10-01')

    def test_freshness_and_mixed_units(self):
        r=rule(); r['definition']['data_freshness_days']=0
        self.assertEqual(resolve_actual(r,self.record(),as_of=date(2026,10,15))['evaluation']['result'],'Unable to Assess')
        r=rule('total_debt',4.5,'x',method='ratio',numerator='total_debt',denominator='ebitda')
        record=self.record(rules=[r]); record['entities']['financial'][0]['attributes']['ebitda']['unit']='INR'
        self.assertEqual(resolve_actual(r,record,as_of=AS_OF)['evaluation']['result'],'Unable to Assess')

    def test_documentary_and_manual_coverage(self):
        r=rule(); r['definition']['evidence_requirements']=[{'key':'approval','type':'approval'}]
        report=coverage_report([r],self.record())
        self.assertFalse(report['rules'][0]['executable'])
        self.assertEqual(sum(report['counts'].values()),1)
        r['definition']['calculation_logic']['method']='manual'
        r['definition']['evidence_requirements']=[]
        self.assertEqual(coverage_report([r],self.record())['counts']['manual_documentary'],1)
