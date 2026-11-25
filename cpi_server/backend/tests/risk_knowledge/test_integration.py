import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.routers import risk_knowledge as router_module
from app.config import RISK_SCHEMA_DIR
from app.risk_knowledge.catalog import documents_from_catalog, project_catalog
from app.risk_knowledge.graph import InMemoryGraphRepository
from app.risk_knowledge.repositories import PostgreSQLRepository
from app.risk_knowledge.service import IntelligenceService


class IntegrationTests(unittest.TestCase):
    def test_normal_initialization_loads_no_manufactured_data(self):
        with tempfile.TemporaryDirectory() as directory:
            service=IntelligenceService(Path(directory)/'state.sqlite3',Path(directory)/'sources')
            source=RISK_SCHEMA_DIR / 'Risk Data Model_Oct 2026.xlsx'
            service.bootstrap(source)
            state=service.state()
            self.assertEqual(state['counts']['source_attributes'],4506)
            self.assertEqual(state['counts']['source_entities'],197)
            self.assertEqual(state['rules'],[])
            self.assertEqual(state['ontology'],[])
            self.assertEqual(len(state['documents']),1)
            self.assertFalse(state['documents'][0]['synthetic'])
            self.assertTrue(all(c['status']=='SOURCE' for c in service.repo.all('taxonomy_concepts')))

    def test_private_postgres_queries_are_bound_to_authenticated_owner(self):
        factory=MagicMock()
        db=factory.return_value.__enter__.return_value
        db.execute.return_value.fetchone.return_value=None
        repository=PostgreSQLRepository(factory,'manager-one')
        repository.get('rule_evaluation_results','same-id')
        self.assertEqual(db.execute.call_args.args[1],('rule_evaluation_results','manager-one','same-id'))
        repository.get('taxonomy_concepts','shared-concept')
        self.assertEqual(db.execute.call_args.args[1],('taxonomy_concepts','','shared-concept'))

    def test_read_and_write_routes_require_existing_cpi_authentication(self):
        app=FastAPI()
        app.include_router(router_module.router)
        def anonymous():raise HTTPException(401,'Authentication required')
        app.dependency_overrides[router_module.current_user]=anonymous
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/risk-knowledge/state').status_code,401)
            self.assertEqual(client.post('/api/risk-knowledge/taxonomy/enrich').status_code,401)

    def test_relationship_manager_cannot_mutate_shared_knowledge(self):
        app=FastAPI()
        app.include_router(router_module.router)
        app.dependency_overrides[router_module.current_user]=lambda:{'user_id':'manager','role':'relationship_manager'}
        app.dependency_overrides[router_module.get_service]=lambda:None
        with TestClient(app) as client:
            self.assertEqual(client.post('/api/risk-knowledge/taxonomy/enrich').status_code,403)
            response=client.post('/api/risk-knowledge/review/taxonomy/test',json={'status':'APPROVED','reviewer':'impersonation','notes':'Trying to approve'})
            self.assertEqual(response.status_code,403)

    def test_review_attribution_comes_from_session(self):
        service=MagicMock()
        service.review.return_value={'status':'APPROVED'}
        app=FastAPI()
        app.include_router(router_module.router)
        app.dependency_overrides[router_module.current_user]=lambda:{'user_id':'actual-analyst','role':'credit_analyst'}
        app.dependency_overrides[router_module.get_service]=lambda:service
        with patch('app.risk_knowledge.semantic_pipeline.review_rule',return_value={'status':'APPROVED'}) as review, \
             patch('app.routers.risk_knowledge.semantic_repository',return_value=service.repo), TestClient(app) as client:
            response=client.post('/api/risk-knowledge/semantic-rules/review',json={'rule_id':'urn:rule:1','expected_digest':'current','status':'APPROVED','notes':'Reviewed source evidence'})
            self.assertEqual(response.status_code,200)
        self.assertEqual(review.call_args.kwargs['actor'],'actual-analyst')
        service.review.assert_not_called()

    def catalog_fixture(self):
        policy={'policy_id':7,'title':'Existing CPI policy','file_name':'policy.txt','document_format':'txt','version':'2',
                'effective_date':None,'source_type':'uploaded','summary':'Current catalog summary','local_pdf_path':None,'status':'Active'}
        clause={'id':9,'policy_id':7,'version':'2','title':policy['title'],'source_excerpt':'Exact governed policy clause.',
                'section_heading':'Approval','page_number':3,'clause_number':'1.2','sequence':1,'document_id':5}
        rule={'id':12,'policy_id':7,'clause_id':9,'title':policy['title'],'policy_version':'2','status':'Approved','active':False,
              'review_required':False,'definition':{'rule_name':'Existing governed requirement','applicability_conditions':{'field':'exposure','operator':'greater_than','value':100}},'rule_code':'R-12'}
        return [policy],[clause],[rule]

    def test_existing_inventory_is_projected_without_reapproval_or_reinterpretation(self):
        graph=InMemoryGraphRepository()
        policies,clauses,rules=self.catalog_fixture()
        original=copy.deepcopy(rules)
        project_catalog(graph,policies,clauses,rules)
        self.assertEqual(rules,original)
        node=graph.nodes['CPI-RULE-12']
        self.assertEqual(node['type'],'GovernedPolicyRule')
        self.assertFalse(node['payload']['active'])
        self.assertTrue(any(e['predicate']=='DERIVED_FROM' and e['provenance']['passage']=='Exact governed policy clause.' for e in graph.edges))
        # Existing governed rules cannot enter the supplemental knowledge-rule evaluator.
        self.assertEqual(graph.approved_rule_ids(),[])

    def test_missing_clause_is_not_fabricated(self):
        graph=InMemoryGraphRepository()
        policies,clauses,rules=self.catalog_fixture()
        project_catalog(graph,policies,[],rules)
        self.assertFalse(any(e['predicate']=='DERIVED_FROM' for e in graph.edges))
        self.assertFalse(any(n['type']=='PolicyClause' for n in graph.nodes.values()))

    def test_reprojecting_existing_catalog_is_idempotent(self):
        graph=InMemoryGraphRepository()
        catalog=self.catalog_fixture()
        project_catalog(graph,*catalog)
        first=graph.snapshot()
        project_catalog(graph,*catalog)
        self.assertEqual(graph.snapshot(),first)

    def test_catalog_summary_is_not_presented_as_extracted_policy_wording(self):
        policies,_,_=self.catalog_fixture()
        document=documents_from_catalog(policies,[])[0]
        self.assertTrue(document['metadata']['raw_text_is_catalog_summary'])
        self.assertEqual(document['document_id'],'CPI-POLICY-7')


if __name__=='__main__':unittest.main()
