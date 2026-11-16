import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from app.risk_knowledge.repositories import SQLiteRepository
from app.risk_knowledge.semantic_pipeline import process_source,current_records
from app.risk_knowledge.semantic_extraction import assemble_graph,rule_id
from app.risk_knowledge.semantic_model import validate_instance
from app.risk_knowledge.semantic_view import graph_view
from risk_knowledge.test_semantic_extraction import fixture


class SemanticGraphNavigationTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        repo=SQLiteRepository(Path(temp.name)/'graph.sqlite3')
        policy,version,clauses,rule,exception=fixture()
        def provider(context):
            return {'rules':[rule.model_dump(),exception.model_dump()],
                    'coverage':[{'clause_id':c['id'],'disposition':'RULES','reason':'Explicit requirement'} for c in clauses]}
        process_source(policy,version,clauses,repo,provider=provider)
        self.records=current_records(repo)
        self.rule=rule_id(7,1,1)

    def test_policy_opens_its_rules_with_provenance_and_explicit_navigation_path(self):
        before=assemble_graph(self.records)
        graph=graph_view(self.records,policy_id=1)
        rules={n['id'] for n in graph['nodes'] if n['type']=='PolicyRule'}
        self.assertIn(self.rule,rules)
        edge=next(e for e in graph['edges'] if e['source']=='urn:cpi:policy:1' and e['target']==self.rule)
        self.assertEqual(edge['predicate'],'CONTAINS_RULE')
        self.assertTrue(edge['derived']);self.assertEqual(edge['via'],['urn:cpi:version:7'])
        self.assertTrue(edge['provenance']['passage'])
        self.assertEqual(assemble_graph(self.records),before)
        self.assertTrue(validate_instance(before)['conforms'])

    def test_rule_reveals_business_values_and_threshold_leads_to_metric(self):
        graph=graph_view(self.records,focus=self.rule)
        types={n['type'] for n in graph['nodes']}
        self.assertTrue({'Product','CustomerSegment','RiskMetric','Threshold','Exception'}<=types)
        threshold=next(n for n in graph['nodes'] if n['type']=='Threshold')
        self.assertEqual(threshold['payload'],{'operator':'LTE','value':75.0,'unit':'%'})
        detail=graph_view(self.records,focus=threshold['id'])
        self.assertTrue(any(e['predicate']=='MEASURED_BY' for e in detail['edges']))

    def test_exception_leads_to_approval_and_credit_authority(self):
        graph=graph_view(self.records,focus=self.rule)
        exception=next(n for n in graph['nodes'] if n['type']=='Exception')
        details=graph_view(self.records,focus=exception['id'])
        approval=next(n for n in details['nodes'] if n['type']=='ApprovalRequirement')
        authority=graph_view(self.records,focus=approval['id'])
        self.assertTrue(any(n['type']=='ApprovalAuthority' and n['label']=='CR' for n in authority['nodes']))
        self.assertTrue(any(e['predicate']=='REQUIRES_APPROVAL_FROM' for e in authority['edges']))

    def test_every_neighbor_is_accessible_across_small_pages(self):
        full=graph_view(self.records,focus=self.rule)
        expected={n['id'] for n in full['neighbors']};seen=set();offset=0
        while True:
            page=graph_view(self.records,focus=self.rule,offset=offset,limit=2)
            self.assertLessEqual(len(page['nodes']),3)
            seen.update(n['id'] for n in page['nodes'] if n['id']!=self.rule)
            if page['next_offset'] is None:break
            offset=page['next_offset']
        self.assertEqual(seen,expected)

    def test_unpublished_rule_is_absent_from_policy_graph(self):
        records=copy.deepcopy(self.records)
        records[0]['rules'][0]['status']='PROPOSED'
        graph=graph_view(records,policy_id=1)
        self.assertNotIn(self.rule,{n['id'] for n in graph['neighbors']})
