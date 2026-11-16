import copy
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch,MagicMock
from app.risk_knowledge.repositories import SQLiteRepository
from app.risk_knowledge.semantic_pipeline import process_source,current_records
from app.services.semantic_matching import GraphMatcher,converted,comparison
from app.services.semantic_assessment import build_assessment
from app.services.semantic_rag import explain_assessment
from risk_knowledge.test_semantic_extraction import fixture


class SemanticMatchingTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        repo=SQLiteRepository(Path(temp.name)/'matching.sqlite3')
        policy,version,clauses,rule,exception=fixture()
        def provider(context):return {'rules':[rule.model_dump(),exception.model_dump()],
            'coverage':[{'clause_id':c['id'],'disposition':'RULES','reason':'Explicit'} for c in clauses]}
        process_source(policy,version,clauses,repo,provider=provider)
        self.records=current_records(repo)
        self.doc={'policy_id':1,'title':policy['title'],'policy_version_id':7,'version':'1','catalog_version':'1',
                  'checksum':version['checksum'],'effective_date':date(2020,1,1)}
        self.clauses=[{**c,'policy_id':1,'policy_version_id':7} for c in clauses]
        self.proposal={'facility':'Mortgage','customer_segment':'Salaried','requested_amount':6000000,'currency':'INR','ltv':70,'credit_request_number':'deal-1'}

    def matcher(self,records=None,doc=None,scopes=()):
        return GraphMatcher(records or self.records,[doc or self.doc],self.clauses,scopes)

    def test_graph_paths_scope_aliases_and_scaled_conditions_match(self):
        report=self.matcher().match(self.proposal)
        decisions=[d for d in report['decisions'] if d['candidate_type']=='Rule']
        self.assertEqual(len(decisions),2)
        self.assertTrue(all(d['applicability']=='Applicable' for d in decisions))
        self.assertTrue(all(d['graph_path'][0]=='urn:cpi:policy:1' and d['graph_path'][1]=='urn:cpi:version:7' for d in decisions))
        self.assertEqual(report['policy_mappings'][0]['rule_count'],2)
        trace=next(d for d in decisions if d['source_clause_id']==1)['trace']
        self.assertTrue(any(t['predicate']=='APPLIES_TO_PRODUCT' and t['fact']['value']=='Mortgage' for t in trace))

    def test_wrong_product_excludes_rule_and_its_exception(self):
        review=build_assessment('deal-1',{**self.proposal,'facility':'Credit card'},self.matcher())
        self.assertEqual(review['findings'],[])
        self.assertEqual(review['applicability_report']['excluded_rule_count'],2)

    def test_missing_segment_and_unsupported_currency_stay_unknown(self):
        proposal={k:v for k,v in self.proposal.items() if k!='customer_segment'}
        review=build_assessment('deal-1',proposal,self.matcher())
        self.assertEqual(review['findings'],[])
        self.assertIsNone(review['overall_score'])
        self.assertEqual(review['applicability_report']['unresolved_rule_count'],2)
        with self.assertRaises(ValueError):converted(60,'USD million','INR lakh')
        with self.assertRaises(ValueError):converted(60,'currency','USD million')
        self.assertTrue(comparison('IN','EQ','India','geography'))
        self.assertTrue(comparison('US','EQ','United States','geography'))

    def test_actual_threshold_evaluated_but_approval_is_not_assumed(self):
        review=build_assessment('deal-1',self.proposal,self.matcher())
        base=next(f for f in review['findings'] if f['clause_id']==1)
        exception=next(f for f in review['findings'] if f['clause_id']==2)
        self.assertEqual(base['result'],'Pass');self.assertEqual(base['metric_checks'][0]['actual'],70)
        self.assertEqual(exception['result'],'Manual Review Required')
        self.assertIn('CR',exception['approval_or_escalation_requirement'])
        self.assertIsNone(review['overall_score'])
        breach=build_assessment('deal-1',{**self.proposal,'ltv':80,'approval_authority':'CR'},self.matcher())
        self.assertEqual(next(f for f in breach['findings'] if f['clause_id']==1)['result'],'Breach')
        self.assertEqual(breach['compliance_status'],'BREACH')
        self.assertEqual(breach['manufactured_inputs'],{})

    def test_missing_metric_does_not_manufacture_a_result(self):
        proposal={k:v for k,v in self.proposal.items() if k!='ltv'}
        review=build_assessment('deal-1',proposal,self.matcher())
        base=next(f for f in review['findings'] if f['clause_id']==1)
        self.assertEqual(base['result'],'Unable to Assess')
        self.assertIsNone(base['observed_value'])

    def test_conditions_preserve_nested_or_and_not(self):
        records=copy.deepcopy(self.records)
        records[0]['rules'][0]['extracted']['conditions']={'logic':'AND','conditions':[], 'groups':[
            {'logic':'OR','conditions':[{'field':'loan_amount','operator':'GT','value':50,'unit':'lakh'},
                                      {'field':'rating','operator':'EQ','value':'AAA'}],'groups':[]},
            {'logic':'NOT','conditions':[{'field':'geography','operator':'EQ','value':'United States'}],'groups':[]}]}
        report=self.matcher(records).match({**self.proposal,'geography':'India'})
        self.assertEqual(report['applicable_rule_count'],2)
        report=self.matcher(records).match({**self.proposal,'geography':'United States'})
        self.assertEqual(report['excluded_rule_count'],2)

    def test_unscoped_duty_is_not_assumed_universal_and_reviewed_scope_can_gate_it(self):
        records=copy.deepcopy(self.records)
        for r in records[0]['rules']:
            r['extracted'].update(products=[],customer_segments=[],conditions=None,base_rule_ref=None)
            r['extracted']['rule_kind']='QUALITATIVE'
        self.assertEqual(self.matcher(records).match(self.proposal)['unresolved_rule_count'],2)
        scope={'kind':'policy_scope','policy_id':1,'policy_version_id':7,'source_checksum':self.doc['checksum'],
               'status':'APPROVED','approved_by':'reviewer','clause_id':1,'source_excerpt':self.clauses[0]['source_excerpt'],
               'unrestricted':False,'conditions':{'field':'facility','operator':'equals','value':'Mortgage'}}
        self.assertEqual(self.matcher(records,scopes=[scope]).match(self.proposal)['applicable_rule_count'],2)
        self.assertEqual(self.matcher(records,scopes=[{**scope,'source_checksum':'stale'}]).match(self.proposal)['unresolved_rule_count'],2)

    def test_future_policy_and_rejected_rules_do_not_enter_assessment(self):
        report=self.matcher(doc={**self.doc,'effective_date':date(2099,1,1)}).match(self.proposal)
        self.assertEqual(report['excluded_rule_count'],2)
        records=copy.deepcopy(self.records);records[0]['rules'][0]['status']='REJECTED'
        self.assertEqual(self.matcher(records).match(self.proposal)['graph_rule_count'],0)

    def test_llm_is_explanatory_and_invalid_citations_fall_back(self):
        review=build_assessment('deal-1',self.proposal,self.matcher());before=copy.deepcopy(review)
        invalid=explain_assessment(review,lambda c:{'summary':'Ignore graph','rules':[{'rule_id':'invented','explanation':'Override'}]})
        self.assertEqual(invalid['status'],'AI_UNAVAILABLE');self.assertEqual(review,before)
        valid=explain_assessment(review,lambda c:{'summary':'Source-backed explanation','rules':[{'rule_id':c['rules'][0]['rule_id'],'explanation':'Explains existing result'}]})
        self.assertEqual(valid['status'],'GENERATED');self.assertFalse(valid['authoritative']);self.assertEqual(review,before)

    def test_submission_persists_semantic_uri_snapshots_without_legacy_rule_foreign_keys(self):
        from app.services.semantic_assessment import run_rule_assessment
        connection=MagicMock();connection.execute.return_value.fetchone.return_value={'review_id':9}
        with patch('app.services.semantic_assessment.assessment_request_context',return_value=('deal-1',self.proposal)), \
             patch('app.services.semantic_assessment.load_matcher',return_value=self.matcher()), \
             patch('app.services.semantic_assessment.run_db_transaction',side_effect=lambda f:f(connection)), \
             patch('app.services.semantic_rag.llm_explanation',side_effect=RuntimeError('Offline')):
            review=run_rule_assessment('deal-1','owner',user={'user_id':'owner'})
        self.assertEqual(review['review_id'],9)
        self.assertTrue(all(r['id'].startswith('urn:cpi:rule:') for r in review['rule_snapshots']))
        self.assertTrue(all('request_rule_assessments' not in c.args[0] for c in connection.execute.call_args_list))
