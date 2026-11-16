import copy
import unittest
from app.services.semantic_assessment import build_assessment
from app.manufacture_data.semantic_actuals import manufacture_actuals
from risk_knowledge import test_semantic_matching as fixtures


class SemanticActualTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.SemanticMatchingTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)

    def test_missing_numeric_actual_gets_reproducible_labeled_sample(self):
        f=self.fixture;proposal={k:v for k,v in f.proposal.items() if k!='ltv'}
        before=copy.deepcopy(proposal);matcher=f.matcher()
        review=build_assessment('deal-1',proposal,matcher,manufacture_missing=True)
        again=build_assessment('deal-1',proposal,matcher,manufacture_missing=True)
        base=next(r for r in review['findings'] if r['clause_id']==1)
        self.assertIsNotNone(base['observed_value'])
        self.assertIn(base['result'],('Pass','Breach'))
        self.assertEqual(review['manufactured_inputs'],again['manufactured_inputs'])
        self.assertEqual(proposal,before)
        self.assertEqual(review['assessment_mode'],'DEMONSTRATION')
        self.assertEqual(base['rule_category'],'QUANTITATIVE')
        self.assertEqual(base['actual_sources'],['SYNTHETIC'])
        evidence=next(e for e in base['evidence_references'] if e['key']=='ltv')
        self.assertEqual(evidence['provenance']['verification_status'],'MANUFACTURED')
        self.assertTrue(evidence['reference'].startswith('semantic-demonstration-actuals-v1:'))

    def test_existing_values_are_preserved_and_qualitative_sample_does_not_grant_approval(self):
        f=self.fixture
        review=build_assessment('deal-1',f.proposal,f.matcher(),manufacture_missing=True)
        base=next(r for r in review['findings'] if r['clause_id']==1)
        qualitative=next(r for r in review['findings'] if r['clause_id']==2)
        self.assertEqual(base['observed_value'],70)
        self.assertNotIn('SYNTHETIC',base['actual_sources'])
        self.assertEqual(review['manufactured_inputs'],{})
        self.assertEqual(qualitative['rule_category'],'QUALITATIVE')
        self.assertEqual(qualitative['result'],'Manual Review Required')
        self.assertIn('verification pending',qualitative['actual'])
        self.assertIn('CR',qualitative['approval_or_escalation_requirement'])

    def test_same_metric_sample_is_shared_by_rules_with_different_thresholds(self):
        f=self.fixture;records=copy.deepcopy(f.records)
        extra=copy.deepcopy(records[0]['rules'][0]);extra['id']+=':other'
        extra['extracted']['thresholds'][0]['value']=80
        records[0]['rules'].append(extra)
        proposal={k:v for k,v in f.proposal.items() if k!='ltv'}
        review=build_assessment('deal-1',proposal,f.matcher(records),manufacture_missing=True)
        observations=[r['observed_value'] for r in review['findings'] if r['rule_category']=='QUANTITATIVE']
        self.assertEqual(len(observations),2);self.assertEqual(observations[0],observations[1])

    def test_generation_never_changes_which_rules_match(self):
        f=self.fixture;proposal={k:v for k,v in f.proposal.items() if k!='customer_segment'}
        plain=build_assessment('deal-1',proposal,f.matcher())
        demo=build_assessment('deal-1',proposal,f.matcher(),manufacture_missing=True)
        self.assertEqual(plain['applicability_report'],demo['applicability_report'])
        self.assertEqual(demo['findings'],[]);self.assertEqual(demo['manufactured_inputs'],{})

    def test_stored_canonical_metric_is_preserved_without_supporting_ratio_inputs(self):
        f=self.fixture
        proposal={**f.proposal,'_canonical_record':{'request_id':'deal-1','entities':{'metric':[{'entity_id':'metrics',
            'attributes':{'ltv_percent':{'value':65,'unit':'%','provenance':{'source_type':'BANK_SYSTEM'}}}}]}}}
        from app.services.semantic_matching import Facts
        actual,unit,source=Facts(proposal).get('ltv')
        self.assertEqual(actual,65);self.assertEqual(unit,'%')
        self.assertEqual(source['provenance']['source_type'],'BANK_SYSTEM')

    def test_conflicting_actuals_are_not_replaced_with_samples(self):
        f=self.fixture;records=copy.deepcopy(f.records)
        rule=records[0]['rules'][0]['extracted']
        rule['metrics'][0]['key']='interest_coverage_ratio'
        rule['thresholds'][0]['metric_key']='interest_coverage_ratio'
        proposal={**f.proposal,'icr':1,'interest_coverage_ratio':2}
        matcher=f.matcher(records);report=matcher.match(proposal)
        decisions=[d for d in report['decisions'] if d['candidate_type']=='Rule' and d['applicability']=='Applicable']
        self.assertEqual(len(decisions),2)
        self.assertEqual(manufacture_actuals('deal-1',proposal,matcher,decisions),{})
