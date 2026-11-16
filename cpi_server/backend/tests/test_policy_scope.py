import copy
import unittest
from datetime import date
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from app.risk_knowledge.graph import NetworkXGraphRepository
from app.risk_knowledge.catalog import project_catalog
from app.services.policy_scope import policy_first_applicability, valid_scope
from app.services.policy_scope_governance import PolicyScopeInput, approve_scope

TODAY = date(2026, 11, 10)


def knowledge():
    policies = [{'policy_id':1,'title':'Term loans','version':'1','summary':'Applies to term loans.'}]
    clauses = [{'id':10,'policy_id':1,'policy_version_id':20,'title':'Term loans','version':'1',
                'source_excerpt':'Applies to term loans. Excludes recovery.', 'sequence':1,'document_id':30,'checksum':'checksum'}]
    rules = [{'id':100,'policy_id':1,'policy_version_id':20,'policy_version':'1','clause_id':10,
              'status':'Approved','approved_by':'reviewer','active':True,'review_required':False,
              'effective_from':'2020-01-01','definition':{'rule_name':'Exposure cap',
              'applicability_conditions':{'field':'currency','operator':'equals','value':'USD'}}}]
    scope = {'kind':'policy_scope','policy_id':1,'policy_version_id':20,'source_checksum':'checksum',
             'clause_id':10,'status':'APPROVED','approved_by':'reviewer',
             'source_excerpt':'Applies to term loans.','conditions':{'field':'facility','operator':'equals','value':'Term Loan'},
             'source':{'document_id':'CPI-POLICY-1','document_name':'Term loans','origin':'REVIEWED_POLICY_SCOPE',
                       'passage':'Applies to term loans.','version':'1'}}
    graph = NetworkXGraphRepository()
    project_catalog(graph, policies, clauses, rules, scopes=[scope])
    return {'policies':policies,'clauses':clauses,'rules':rules,'graph':graph,'scopes':{1:scope},
            'versions':{1:{'id':20,'checksum':'checksum','effective_date':date(2020,1,1)}},
            'concepts':[],'fingerprint':'frozen-source'}


class DeterministicGraphApplicabilityTests(unittest.TestCase):
    def setUp(self):
        self.knowledge = knowledge()

    def run_report(self, data=None):
        with patch('app.ai_provider.AIClient', side_effect=AssertionError('LLM must never select rules')):
            return policy_first_applicability(data if data is not None else {'facility':'Term Loan','currency':'USD'},
                                             self.knowledge['rules'],'In Review',TODAY,knowledge=self.knowledge)

    def test_graph_selects_approved_rule_and_records_exact_path(self):
        report = self.run_report()
        self.assertEqual([d['applicability'] for d in report['decisions']], ['Applicable','Applicable'])
        self.assertEqual(report['decisions'][1]['graph_path'], ['CPI-POLICY-1','CPI-CLAUSE-10','CPI-RULE-100'])
        self.assertEqual(report['policy_mappings'][0]['rule_version_ids'], [100])
        self.assertFalse(report['retrieval']['llm_used'])
        self.assertEqual(report, self.run_report())

    def test_policy_exclusion_precedes_rule_check(self):
        report = self.run_report({'facility':'Overdraft','currency':'USD'})
        self.assertEqual([d['applicability'] for d in report['decisions']], ['Not Applicable','Not Applicable'])
        self.assertEqual(report['policy_mappings'], [])

    def test_rule_mismatch_never_changes_policy_scope(self):
        report = self.run_report({'facility':'Term Loan','currency':'EUR'})
        self.assertEqual([d['applicability'] for d in report['decisions']], ['Applicable','Not Applicable'])
        self.assertEqual(report['policy_mappings'][0]['rule_count'], 0)

    def test_missing_request_attributes_remain_unknown(self):
        report = self.run_report({})
        self.assertEqual([d['applicability'] for d in report['decisions']], ['Unable to Determine']*2)
        self.assertIn('facility', report['decisions'][0]['missing_information'])

    def test_missing_rule_attribute_remains_unknown(self):
        report = self.run_report({'facility':'Term Loan'})
        self.assertEqual(report['decisions'][1]['applicability'], 'Unable to Determine')

    def test_unapproved_missing_stale_or_unsupported_scope_is_never_guessed(self):
        for change in ({'status':'AI_PROPOSED'}, {'approved_by':None}, {'source_checksum':'changed'},
                       {'policy_version_id':99}, {'source_excerpt':'Invented passage'},
                       {'conditions':None}, {'conditions':{'field':'facility'}}, {'clause_id':99}):
            with self.subTest(change=change):
                self.knowledge = knowledge()
                self.knowledge['scopes'][1].update(change)
                self.assertEqual(self.run_report()['decisions'][0]['applicability'], 'Unable to Determine')
        self.knowledge['scopes'] = {}
        self.assertEqual(self.run_report()['unresolved_policy_count'], 1)

    def test_explicit_exclusion_blocks_and_missing_exclusion_is_unknown(self):
        self.knowledge['scopes'][1]['exclusions'] = {'field':'recovery','operator':'equals','value':True}
        self.assertEqual(self.run_report({'facility':'Term Loan','recovery':True})['decisions'][0]['applicability'], 'Not Applicable')
        self.assertEqual(self.run_report()['decisions'][0]['applicability'], 'Unable to Determine')

    def test_only_explicitly_approved_unrestricted_scope_can_omit_conditions(self):
        self.knowledge['scopes'][1].update(conditions=None, unrestricted=True)
        self.assertEqual(self.run_report({'currency':'USD'})['decisions'][0]['applicability'], 'Applicable')

    def test_future_policy_and_out_of_date_rule_are_excluded(self):
        self.knowledge['versions'][1]['effective_date'] = date(2027,1,1)
        self.assertEqual(self.run_report()['decisions'][0]['applicability'], 'Not Applicable')
        self.knowledge = knowledge()
        self.knowledge['rules'][0]['effective_to'] = '2026-01-01'
        self.assertEqual(self.run_report()['decisions'][1]['applicability'], 'Not Applicable')

    def test_wrong_direction_missing_source_and_unapproved_graph_nodes_do_not_select(self):
        original = self.knowledge['graph'].snapshot()
        for mode in ('reverse','missing','candidate','stale'):
            with self.subTest(mode=mode):
                snapshot = copy.deepcopy(original)
                for edge in snapshot['edges']:
                    if edge['source']=='CPI-RULE-100' and edge['predicate']=='DERIVED_FROM':
                        if mode=='reverse': edge['source'],edge['target']=edge['target'],edge['source']
                        elif mode=='missing': edge['predicate']='MAPS_TO'
                for node in snapshot['nodes']:
                    if node['id']=='CPI-RULE-100':
                        if mode=='candidate': node['status']='CANDIDATE'
                        elif mode=='stale': node['payload']['review_required']=True
                self.knowledge['graph'].replace(snapshot['nodes'], snapshot['edges'])
                self.assertEqual(self.run_report()['decisions'][1]['applicability'], 'Unable to Determine')

    def test_unresolved_rule_mapping_does_not_override_confirmed_exclusion(self):
        self.knowledge['rules'][0]['definition']['applicability_unresolved'] = True
        self.assertEqual(self.run_report({'facility':'Term Loan','currency':'EUR'})['decisions'][1]['applicability'], 'Not Applicable')

    def test_approved_taxonomy_synonyms_are_normalized_and_original_input_is_preserved(self):
        source = {'document_id':'schema','document_name':'Schema','origin':'SOURCE_SCHEMA','passage':'Product'}
        field = {'concept_id':'facility','preferred_name':'Facility','kind':'ATTRIBUTE','status':'APPROVED',
                 'metadata':{'request_attribute':'facility'},'source':source,'data_type':'string','allowed_values':['Term Loan']}
        value = {'concept_id':'term','preferred_name':'Term Loan','kind':'VALUE','status':'APPROVED',
                 'metadata':{'request_attribute':'facility'},'source':source,'synonyms':['term financing']}
        self.knowledge['concepts'] = [field,value]
        request = {'facility':'term financing','currency':'USD'}
        result = self.run_report(request)
        self.assertEqual(result['decisions'][0]['applicability'], 'Applicable')
        self.assertEqual(result['taxonomy_normalization'][0]['original_term'], 'term financing')
        self.assertEqual(request['facility'], 'term financing')

    def test_ontology_relationship_cannot_establish_absent_policy_scope(self):
        self.knowledge['scopes'] = {}
        snapshot = self.knowledge['graph'].snapshot()
        snapshot['edges'].append({'id':'ontology','source':'CPI-RULE-100','target':'CPI-POLICY-1',
                                  'predicate':'APPLIES_TO','status':'APPROVED','provenance':{'passage':'A relationship is not a scope condition'}})
        self.knowledge['graph'].replace(snapshot['nodes'],snapshot['edges'])
        self.assertEqual(self.run_report()['decisions'][0]['applicability'], 'Unable to Determine')

    def test_request_graph_uses_only_current_semantic_graph(self):
        from app.routers.risk_knowledge import request_graph
        from types import SimpleNamespace
        report={'decisions':[{'candidate_id':'urn:rule:1','candidate_type':'Rule','applicability':'Applicable'}]}
        matcher=SimpleNamespace(records=[],fingerprint='current',match=lambda data:report)
        view={'nodes':[{'id':'urn:rule:1'}],'edges':[]}
        with patch('app.services.rule_assessment.assessment_request_context',return_value=('req',{})), \
             patch('app.services.semantic_matching.load_matcher',return_value=matcher), \
             patch('app.risk_knowledge.semantic_view.graph_view',return_value=view) as graph:
            result=request_graph('req',focus='urn:rule:1',user={'user_id':'analyst'})
        graph.assert_called_once_with([],focus='urn:rule:1')
        self.assertEqual(result['nodes'][0]['applicability'],'Applicable')
        self.assertEqual(result['knowledge_fingerprint'],'current')

    def test_request_graph_denied_access_does_not_read_graph_or_evaluate(self):
        from app.routers.risk_knowledge import request_graph
        with patch('app.services.rule_assessment.assessment_request_context',side_effect=HTTPException(404,'Unavailable')), \
             patch('app.services.policy_scope.load_knowledge') as load:
            with self.assertRaises(HTTPException): request_graph('other',user={'user_id':'analyst'})
        load.assert_not_called()


class ScopeApprovalTests(unittest.TestCase):
    def context(self):
        return {'policy':{'id':20,'policy_id':1,'checksum':'checksum','version':'1','title':'Term loans'},
                'clauses':knowledge()['clauses'],'scope':None}

    def body(self, **kwargs):
        return PolicyScopeInput(**{'policy_version_id':20,'clause_id':10,'source_excerpt':'Applies to term loans.',
                                  'conditions':{'field':'facility','operator':'equals','value':'Term Loan'},
                                  'notes':'Reviewed scope and exclusions',**kwargs})

    def test_approval_preserves_version_source_and_audited_identity(self):
        with patch('app.services.policy_scope_governance.scope_context', return_value=self.context()), \
             patch('app.services.policy_scope_governance.PostgreSQLRepository') as repo:
            result = approve_scope(1,self.body(),{'user_id':'analyst','role':'credit_analyst'})
        self.assertEqual(result['source_checksum'], 'checksum')
        self.assertEqual(result['approved_by'], 'analyst')
        self.assertEqual(repo.return_value.put.call_args.args[3]['action'], 'APPROVE_POLICY_SCOPE')

    def test_reader_cannot_approve(self):
        with self.assertRaises(HTTPException) as error:
            approve_scope(1,self.body(),{'user_id':'rm','role':'relationship_manager'})
        self.assertEqual(error.exception.status_code, 403)

    def test_wrong_version_or_invented_passage_cannot_be_approved(self):
        for change,status in (({'policy_version_id':99},409),({'source_excerpt':'invented'},422),({'clause_id':99},422)):
            with self.subTest(change=change), patch('app.services.policy_scope_governance.scope_context', return_value=self.context()):
                with self.assertRaises(HTTPException) as error:
                    approve_scope(1,self.body(**change),{'user_id':'analyst','role':'admin'})
                self.assertEqual(error.exception.status_code, status)

    def test_absent_scope_requires_explicit_unrestricted_confirmation(self):
        with self.assertRaises(ValueError):
            self.body(conditions=None)
        self.body(conditions=None,unrestricted=True)


if __name__ == '__main__': unittest.main()
