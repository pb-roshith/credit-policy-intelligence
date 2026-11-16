from copy import deepcopy
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app.risk_knowledge.repositories import SQLiteRepository
from app.risk_knowledge.semantic_pipeline import process_source,current_records
from app.risk_knowledge.semantic_scope import Scope,enrich_scope,validate_scope,review_scope
from app.risk_knowledge.semantic_extraction import assemble_graph
from app.risk_knowledge.semantic_model import validate_instance
from app.services.semantic_matching import GraphMatcher
from risk_knowledge.test_semantic_extraction import fixture


class SemanticScopeTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.repo=SQLiteRepository(Path(temp.name)/'scopes.sqlite3')
        policy,version,clauses,rule,exception=fixture()
        self.text='2. Scope\nThis policy applies to all retail credit products. Excludes Credit cards.'
        clauses.append({'id':3,'sequence':3,'source_excerpt':self.text,'page_number':1})
        def provider(context):return {'rules':[rule.model_dump(),exception.model_dump()],
            'coverage':[{'clause_id':c['id'],'disposition':'NON_RULE' if c['id']==3 else 'RULES','reason':'Explicit'} for c in clauses]}
        process_source(policy,version,clauses,self.repo,provider=provider)
        self.record=current_records(self.repo)[0]
        self.scope={'sources':[{'clause_id':3,'quote':self.text}],
            'conditions':{'logic':'AND','conditions':[{'field':'business_line','operator':'EQ','value':'retail','evidence':'retail'}]},
            'exclusions':{'logic':'AND','conditions':[{'field':'product','operator':'EQ','value':'Credit cards','evidence':'Excludes Credit cards.'}]},'unrestricted':False}

    def test_scope_is_published_as_graph_conditions_without_changing_rules(self):
        result=enrich_scope(self.repo,self.record,provider=lambda r,c:self.scope)
        self.assertEqual(result['rules'],self.record['rules'])
        self.assertEqual(result['policy_scope']['status'],'APPROVED')
        graph=assemble_graph([result]);self.assertTrue(validate_instance(graph)['conforms'])
        self.assertTrue(any(e['predicate']=='HAS_APPLICABILITY' and e['subject']=='urn:cpi:version:7' for e in graph['relationships']))

    def test_scope_gate_is_inherited_and_unknown_policy_scope_cannot_be_ignored(self):
        result=enrich_scope(self.repo,self.record,provider=lambda r,c:self.scope)
        doc={'policy_id':1,'title':'Policy','policy_version_id':7,'checksum':result['source_checksum'],'effective_date':date(2020,1,1)}
        matcher=GraphMatcher([result],[doc],[])
        report=matcher.match({'credit_request_number':'r','facility':'Mortgage','customer_segment':'Salaried','requested_amount':6000000,'currency':'INR'})
        self.assertEqual(report['applicable_rule_count'],2)
        result['policy_scope']['conditions']['conditions'][0]['field']='industry'
        matcher=GraphMatcher([result],[doc],[])
        self.assertEqual(matcher.match({'facility':'Mortgage','customer_segment':'Salaried','requested_amount':6000000,'currency':'INR'})['unresolved_rule_count'],2)

    def test_global_geography_never_establishes_universal_credit_scope(self):
        scope=Scope(sources=[{'clause_id':3,'quote':self.text}],unrestricted=True)
        self.assertIn('Universal scope',validate_scope(scope,self.record['source_clauses']))

    def test_invalid_source_is_retained_as_proposed_and_cannot_gate_rules(self):
        candidate=deepcopy(self.scope);candidate['sources'][0]['quote']='Invented quotation'
        result=enrich_scope(self.repo,self.record,provider=lambda r,c:candidate)
        self.assertEqual(result['policy_scope']['status'],'PROPOSED')
        self.assertFalse(any(e['predicate']=='HAS_APPLICABILITY' for e in assemble_graph([result])['relationships']))

    def test_reviewer_override_requires_current_digest_and_preserves_human_decision(self):
        result=enrich_scope(self.repo,self.record,provider=lambda r,c:self.scope)
        with self.assertRaises(ValueError):review_scope(self.repo,1,'stale',self.scope,'APPROVED','analyst','Reviewed')
        reviewed=review_scope(self.repo,1,result['content_digest'],self.scope,'PROPOSED','analyst','Return for correction')
        self.assertTrue(reviewed['human_override'])
        saved=current_records(self.repo)[0]
        refreshed=enrich_scope(self.repo,saved,provider=lambda r,c:self.fail('Must preserve reviewer decision'))
        self.assertEqual(refreshed['policy_scope']['status'],'PROPOSED')
