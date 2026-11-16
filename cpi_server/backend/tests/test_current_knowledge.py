import unittest
from unittest.mock import patch
from app.services.current_knowledge import current_review, current_reviews, policy_controls
from app.services.semantic_assessment import ENGINE_VERSION


class CurrentKnowledgeTests(unittest.TestCase):
    def test_older_method_and_changed_knowledge_cannot_supply_current_scores(self):
        current={'assessment_scope':'current-semantic-graph','engine_version':ENGINE_VERSION,'knowledge_fingerprint':'now'}
        self.assertTrue(current_review(current,'now'))
        self.assertFalse(current_review(current,'earlier'))
        self.assertFalse(current_review({**current,'engine_version':'old'},'now'))
        self.assertFalse(current_review({'overall_score':99},'now'))
        rows=[{'review':current},{'review':{'overall_score':99}},{'review':{**current,'knowledge_fingerprint':'earlier'}}]
        self.assertEqual(current_reviews(rows,'now'),rows[:1])

    def test_controls_are_published_qualitative_rules_without_invented_control_values(self):
        from types import SimpleNamespace
        rule={'id':'urn:rule:1','policy_id':1,'policy_name':'Policy','published_in_graph':True,
              'rule_category':'QUALITATIVE','status':'APPROVED','source':{'clause_number':'1.1','page_number':2},
              'extracted':{'name':'Review collateral','source_quote':'Collateral must be reviewed.', 'approvals':[],'clause_id':1}}
        candidates=[rule,{**rule,'id':'urn:proposed','published_in_graph':False},
                    {**rule,'id':'urn:quantitative','rule_category':'QUANTITATIVE'}]
        with patch('app.services.current_knowledge.inventory',return_value={'rules':candidates}):
            controls=policy_controls(matcher=SimpleNamespace(fingerprint='now'))
        self.assertEqual([c['control_id'] for c in controls],['urn:rule:1'])
        self.assertEqual(controls[0]['control_description'],rule['extracted']['source_quote'])
        self.assertIsNone(controls[0]['control_owner'])
        self.assertNotIn('effectiveness',controls[0])
        self.assertNotIn('frequency',controls[0])

    def test_policy_panel_excludes_extracted_requirements_from_generated_control_count(self):
        from app.routers.policies import policy_controls as panel_controls
        generated=[{'control_id':str(i)} for i in range(5)]
        with patch('app.services.current_knowledge.manufactured_controls',return_value=generated) as load, \
             patch('app.services.current_knowledge.policy_controls') as requirements:
            self.assertEqual(panel_controls(1,{}),generated)
        load.assert_called_once_with(1)
        requirements.assert_not_called()

    def test_related_policies_join_concept_values_and_include_recorded_parent(self):
        from types import SimpleNamespace
        from app.services.current_knowledge import policy_relationships
        docs=[{'policy_id':i,'title':str(i),'library_policy_id':str(i),
               'parent_policy':'Retail' if i in (1,2) else 'Other '+str(i)} for i in (1,2,3,4)]
        graph={'nodes':[{'id':identifier,'type':'RiskMetric','label':'LTV','properties':{'metric_key':key}}
                        for identifier,key in [('metric-in-policy-1','ltv'),('metric-in-policy-3','LTV')]],
               'relationships':[{'subject':'r1','predicate':'USES_METRIC','object':'metric-in-policy-1'},
                                {'subject':'r3','predicate':'USES_METRIC','object':'metric-in-policy-3'}]}
        matcher=SimpleNamespace(graph=graph,rows={'r1':({'policy_id':1},{}),'r3':({'policy_id':3},{})},fingerprint='current')
        with patch('app.database.shared_policy_connection') as db:
            db.return_value.__enter__.return_value.execute.return_value.fetchall.return_value=docs
            result=policy_relationships(1,matcher)
        self.assertEqual({r['related_policy_id'] for r in result},{2,3})
        self.assertIn('Same parent policy: Retail',result[0]['rationale'])
        self.assertIn('Shared metrics: LTV',result[1]['rationale'])
        self.assertTrue(all(r['related_policy_id']!=1 for r in result))

    def test_unknown_parent_and_generic_taxonomy_do_not_create_spurious_relations(self):
        from types import SimpleNamespace
        from app.services.current_knowledge import policy_relationships
        matcher=SimpleNamespace(graph={'nodes':[{'id':'generic','type':'TaxonomyConcept','label':'eligibility',
            'properties':{'taxonomy_id':'PTX-CATEGORY-eligibility'}}],
            'relationships':[{'subject':r,'predicate':'CLASSIFIED_AS','object':'generic'} for r in ('r1','r2')]},
            rows={'r1':({'policy_id':1},{}),'r2':({'policy_id':2},{})},fingerprint='current')
        with patch('app.database.shared_policy_connection') as db:
            db.return_value.__enter__.return_value.execute.return_value.fetchall.return_value=[
                {'policy_id':i,'title':str(i),'parent_policy':'UNKNOWN'} for i in (1,2)]
            self.assertEqual(policy_relationships(1,matcher),[])
