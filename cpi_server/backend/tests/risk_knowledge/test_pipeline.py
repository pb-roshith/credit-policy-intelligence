import copy
import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch,MagicMock
from fastapi import BackgroundTasks,FastAPI,HTTPException
from fastapi.testclient import TestClient
from app.risk_knowledge.models import Concept,Provenance,Mappings,Relationship,RelationshipCandidates
from app.risk_knowledge.llm import MockLLMProvider
from app.risk_knowledge.service import IntelligenceService
from app.risk_knowledge.pipeline import PolicyKnowledgePipeline,PIPELINE_VERSION,process_policy,matching_concepts
from app.routers import risk_knowledge as routes
from app.services.inventory_schema import GovernedDefinition,GovernedRuleInput
from app.services.rule_governance import store_rule


def source_fixture():
    clause={'id':91,'sequence':1,'clause_number':'1.1','section_heading':'Limits','page_number':2,
            'source_excerpt':'Exposure shall not exceed 100 USD.'}
    policy={'policy_id':7,'title':'Selected policy','source_type':'uploaded','local_pdf_path':'registered.txt'}
    version={'id':81,'version':'1','effective_date':date(2026,1,1),'effective_date_source':'source document'}
    document={'id':71,'file_type':'.txt','file_name':'registered.txt','checksum':'source-checksum','source_path':'archive.txt'}
    return policy,version,document,[clause]


def rule_fixture():
    return {'id':101,'clause_id':91,'policy_version_id':81,'policy_id':7,'status':'Draft','active':False,
            'definition':{'rule_name':'Exposure limit','rule_description':'Exposure shall not exceed 100 USD.',
                          'rule_type':'quantitative','metric_name':'exposure','input_data_fields':['exposure'],
                          'calculation_logic':{'method':'direct','field':'exposure'},'operator':'less_than_or_equal',
                          'threshold_value':100,'threshold_unit':None,'threshold_source':'100 USD',
                          'source_excerpt':'Exposure shall not exceed 100 USD.'}}


class PipelineTests(unittest.TestCase):
    def test_retrieval_prefers_actual_financial_terms_over_common_words(self):
        concepts=[{'concept_id':'coverage','preferred_name':'Interest Coverage','synonyms':[]},
                  {'concept_id':'unrelated','preferred_name':'Number of transactions within the session for the year','synonyms':[]}]
        result=matching_concepts(concepts,'For the year, the borrower must maintain minimum interest coverage of 2.5x.',limit=1)
        self.assertEqual(result[0]['concept_id'],'coverage')

    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service=IntelligenceService(Path(self.temp.name)/'state.sqlite3',Path(self.temp.name)/'archive')
        self.events=[]
        self.pipeline=PolicyKnowledgePipeline(self.service,MagicMock(),{'user_id':'analyst'},'job-1',
                    lambda batch,**detail:self.events.append(copy.deepcopy(detail)))
        self.pipeline.prepare_source(source_fixture())

    def add_concept(self,status='APPROVED'):
        concept=Concept(concept_id='EXPOSURE',preferred_name='Exposure',kind='ATTRIBUTE',status=status,
                        source=Provenance(document_id='SCHEMA',document_name='Risk schema',origin='SOURCE_SCHEMA',passage='Exposure field'))
        self.service.repo.put('taxonomy_concepts',concept.concept_id,concept.model_dump())
        return concept

    def test_selected_policy_clauses_are_classified_without_rewriting_source(self):
        self.pipeline.classify()
        clause=self.service.repo.get('clauses','CPI-CLAUSE-91')
        self.assertEqual(clause['raw_text'],'Exposure shall not exceed 100 USD.')
        self.assertEqual(clause['source']['page'],2)
        self.assertEqual(clause['source']['version'],'1')
        self.assertIn('RULE',clause['categories'])
        self.assertTrue(any(e['stage']=='classification' for e in self.events))

    def test_mapping_uses_approved_taxonomy_and_preserves_original_term(self):
        self.add_concept()
        self.pipeline.classify()
        self.pipeline.discover_ontology()
        self.pipeline.annotate([rule_fixture()],source_fixture()[3])
        evidence=self.service.repo.get('metadata','CPI-RULE-101')
        self.assertEqual(evidence['taxonomy_mappings'],[{'original_term':'exposure','concept_id':'EXPOSURE','normalized_term':'Exposure','status':'RESOLVED'}])
        self.assertEqual(evidence['source']['passage'],'Exposure shall not exceed 100 USD.')
        self.assertEqual(evidence['status'],'VALIDATED_CANDIDATE')
        self.assertIsNone(evidence['confidence'])
        self.assertEqual(self.service.repo.all('policy_rules'),[]) # No competing rule library.

    def test_automatic_approval_makes_source_terms_available_for_mapping(self):
        self.add_concept('SOURCE')
        self.pipeline.discover_ontology()
        self.pipeline.annotate([rule_fixture()],source_fixture()[3])
        evidence=self.service.repo.get('metadata','CPI-RULE-101')
        self.assertEqual(evidence['taxonomy_mappings'][0]['status'],'RESOLVED')
        self.assertEqual(self.service.repo.get('taxonomy_concepts','EXPOSURE')['status'],'APPROVED')

    def test_ontology_accepts_exact_subpassages_and_excludes_invented_evidence(self):
        self.add_concept()
        second=Concept(concept_id='USD',preferred_name='USD',status='APPROVED',source=Provenance(
            document_id='SCHEMA',document_name='Risk schema',origin='SOURCE_SCHEMA',passage='USD'))
        self.service.repo.put('taxonomy_concepts','USD',second.model_dump())
        source=self.pipeline.clauses_by_id[91].source
        candidates=RelationshipCandidates(items=[
            Relationship(relationship_id='valid',subject='EXPOSURE',predicate='HAS_UNIT',object='USD',source=source.model_copy(update={'passage':'Exposure shall not exceed 100 USD'})),
            Relationship(relationship_id='invalid',subject='EXPOSURE',predicate='HAS_UNIT',object='USD',source=source.model_copy(update={'passage':'Exposure may reach 200 USD'})),
        ])
        with patch.object(self.service,'call',return_value=candidates):
            self.pipeline.discover_ontology()
        relationships=self.service.repo.all('ontology_relationships')
        self.assertEqual(len(relationships),1)
        self.assertEqual(relationships[0]['source']['passage'],'Exposure shall not exceed 100 USD')
        self.assertEqual(relationships[0]['status'],'APPROVED')
        self.assertTrue(any(item.get('status')=='REJECTED' for item in self.service.repo.all('metadata')))

    def test_invented_mapping_is_rejected_before_annotation_is_saved(self):
        self.pipeline.discover_ontology()
        with patch.object(self.service,'call',return_value=Mappings(items=[{'original_term':'exposure','concept_id':'invented','normalized_term':'Invented'}])):
            with self.assertRaisesRegex(ValueError,'approved concept'):
                self.pipeline.annotate([rule_fixture()],source_fixture()[3])
        self.assertIsNone(self.service.repo.get('metadata','CPI-RULE-101'))

    def test_cached_rules_recover_mapping_stage_idempotently(self):
        self.add_concept()
        self.pipeline.discover_ontology()
        self.pipeline.annotate([rule_fixture()],source_fixture()[3])
        self.pipeline.annotate([rule_fixture()],source_fixture()[3])
        self.assertEqual(self.pipeline.counts['rules_mapped'],1)
        self.assertEqual(len(self.service.repo.all('metadata')),1)

    def test_changed_policy_source_or_version_cannot_be_annotated(self):
        self.pipeline.discover_ontology()
        for row in [rule_fixture()|{'policy_version_id':99},rule_fixture()|{'definition':rule_fixture()['definition']|{'source_excerpt':'Invented requirement'}}]:
            with patch('app.risk_knowledge.pipeline.approve_rules') as approve:
                with self.assertRaisesRegex(ValueError,'exact policy source'):
                    self.pipeline.annotate([row],source_fixture()[3])
                approve.assert_not_called()

    def test_graph_is_built_with_annotations_for_the_same_rule_version(self):
        self.add_concept()
        self.pipeline.discover_ontology()
        self.pipeline.annotate([rule_fixture()],source_fixture()[3])
        catalog=([],[],[])
        with patch('app.risk_knowledge.pipeline.read_catalog',return_value=catalog),patch('app.risk_knowledge.pipeline.project_catalog') as project:
            result=self.pipeline.finish({'status':'Completed','rules_proposed':1})
        self.assertEqual(result['pipeline'],PIPELINE_VERSION)
        self.assertTrue(all(s['status']=='Completed' for s in result['stages'] if s['id'] in ('mapping','validation','graph')))
        project.assert_called_once()

    def test_partial_extraction_builds_graph_for_saved_drafts_and_retains_failure(self):
        self.pipeline.discover_ontology()
        self.pipeline.annotate([rule_fixture()],source_fixture()[3])
        with patch('app.risk_knowledge.pipeline.read_catalog',return_value=([],[],[])),patch('app.risk_knowledge.pipeline.project_catalog') as project:
            result=self.pipeline.finish({'status':'Failed','rules_proposed':1,'error':'One source group failed'},partial=True)
        stages={s['id']:s['status'] for s in result['stages']}
        self.assertEqual(result['status'],'Completed with errors')
        self.assertTrue(result['partial_result'])
        self.assertEqual(stages['extraction'],'Partial')
        self.assertEqual(stages['graph'],'Completed')
        self.assertEqual(result['error'],'One source group failed')
        project.assert_called_once()

    def test_operational_entrypoint_uses_graph_informed_semantic_extraction(self):
        with patch('app.risk_knowledge.semantic_pipeline.process_policy',return_value={'status':'Completed','pipeline':PIPELINE_VERSION}) as compile_policy, \
             patch('app.risk_knowledge.pipeline.PolicyKnowledgePipeline') as legacy:
            result=process_policy(7,{'user_id':'analyst'},'job-1')
        self.assertEqual(result['pipeline'],PIPELINE_VERSION)
        compile_policy.assert_called_once_with(7,{'user_id':'analyst'},'job-1',None)
        legacy.assert_not_called()

    def test_partial_mapping_is_not_reported_as_complete(self):
        self.pipeline.discover_ontology()
        self.pipeline.annotate([rule_fixture()],source_fixture()[3])
        with patch('app.risk_knowledge.pipeline.read_catalog',return_value=([],[],[])),patch('app.risk_knowledge.pipeline.project_catalog'):
            result=self.pipeline.finish({'status':'Failed','rules_proposed':2,'error':'Second rule mapping failed'},partial=True)
        stages={s['id']:s['status'] for s in result['stages']}
        self.assertEqual(stages['mapping'],'Partial')
        self.assertEqual(stages['validation'],'Partial')
        self.assertEqual(result['status'],'Completed with errors')

    def test_source_context_is_available_after_automatic_approval(self):
        self.add_concept('SOURCE')
        self.pipeline.discover_ontology()
        context=self.pipeline.batch_context(source_fixture()[3])
        self.assertEqual(context['approved_taxonomy'][0]['status'],'APPROVED')
        self.assertEqual(context['source_schema'][0]['status'],'APPROVED')

    def test_extraction_context_is_bounded_without_truncating_source_clauses(self):
        concept=self.add_concept()
        concept.allowed_values=['a very long vocabulary value '+str(i) for i in range(2000)]
        self.service.repo.put('taxonomy_concepts',concept.concept_id,concept.model_dump())
        self.pipeline.discover_ontology()
        context=self.pipeline.batch_context(source_fixture()[3])
        self.assertLessEqual(len(json.dumps(context)),18000)
        self.assertEqual(self.pipeline.clauses[0]['source_excerpt'],'Exposure shall not exceed 100 USD.')

    def test_parallel_proposal_creation_cannot_overwrite_reviewed_knowledge(self):
        approved=self.add_concept()
        proposed=approved.model_copy(update={'status':'AI_PROPOSED'})
        created=self.service.repo.put_new('taxonomy_concepts',approved.concept_id,proposed.model_dump())
        self.assertFalse(created)
        self.assertEqual(self.service.repo.get('taxonomy_concepts',approved.concept_id)['status'],'APPROVED')

    def test_changed_source_schema_invalidates_extraction_context_checkpoint(self):
        self.pipeline.load_approved_knowledge()
        initial=self.pipeline.context_fingerprint
        self.add_concept('SOURCE')
        self.pipeline.load_approved_knowledge()
        self.assertNotEqual(initial,self.pipeline.context_fingerprint)

    def test_failed_pipeline_does_not_leave_stages_marked_running(self):
        self.pipeline.stage('mapping')
        self.pipeline.stage('validation')
        self.pipeline.fail()
        self.assertFalse(any(s['status']=='Running' for s in self.pipeline.stages))
        self.assertEqual(next(s for s in self.pipeline.stages if s['id']=='validation')['status'],'Failed')

    def test_batch_workers_initialize_the_shared_schema_only_once(self):
        from concurrent.futures import ThreadPoolExecutor
        schema=Path(self.temp.name)/'schema.xlsx'
        schema.write_bytes(b'bootstrap fixture')
        with patch.object(self.service,'ingest') as ingest:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda _:self.service.bootstrap(schema),range(4)))
        self.assertEqual(ingest.call_count,1)


class ExtractionRouteTests(unittest.TestCase):
    def test_retry_recovers_historical_completed_job_with_partial_results(self):
        identifier='df3067e0-dd00-4cea-84f0-2a3089d431dd'
        actor={'user_id':'analyst','role':'credit_analyst'}
        job={'id':identifier,'status':'Completed','created_by':'analyst','report':{'pipeline':PIPELINE_VERSION},
             'progress':[{'policy_id':1,'status':'Completed','partial_result':True}]}
        with patch.object(routes,'shared_policy_connection') as shared:
            shared.return_value.__enter__.return_value.execute.return_value.fetchone.side_effect=[job,None,job|{'status':'Queued'}]
            result=routes.retry_extraction(identifier,BackgroundTasks(),actor)
        self.assertEqual(result['status'],'Queued')

    def test_retry_reuses_job_id_and_schedules_existing_worker(self):
        identifier='df3067e0-dd00-4cea-84f0-2a3089d431dd'
        actor={'user_id':'analyst','role':'credit_analyst'}
        job={'id':identifier,'status':'Completed with errors','created_by':'analyst','report':{'pipeline':PIPELINE_VERSION}}
        background=BackgroundTasks()
        with patch.object(routes,'shared_policy_connection') as shared:
            connection=shared.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.side_effect=[job,None,job|{'status':'Queued'}]
            result=routes.retry_extraction(identifier,background,actor)
        self.assertEqual(result['id'],identifier)
        self.assertEqual(result['status'],'Queued')
        self.assertEqual(background.tasks[0].args,(identifier,actor))

    def test_retry_rejects_read_only_role_and_other_users_jobs(self):
        identifier='df3067e0-dd00-4cea-84f0-2a3089d431dd'
        with self.assertRaises(HTTPException) as denied:
            routes.retry_extraction(identifier,BackgroundTasks(),{'user_id':'viewer','role':'viewer'})
        self.assertEqual(denied.exception.status_code,403)
        job={'id':identifier,'status':'Completed with errors','created_by':'someone_else','report':{'pipeline':PIPELINE_VERSION}}
        with patch.object(routes,'shared_policy_connection') as shared:
            shared.return_value.__enter__.return_value.execute.return_value.fetchone.side_effect=[job]
            with self.assertRaises(HTTPException) as denied:
                routes.retry_extraction(identifier,BackgroundTasks(),{'user_id':'manager','role':'relationship_manager'})
        self.assertEqual(denied.exception.status_code,403)

    def test_extract_button_endpoint_queues_only_selected_policies_for_existing_worker(self):
        app=FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[routes.current_user]=lambda:{'user_id':'manager','role':'relationship_manager'}
        with patch('app.routers.rules.enqueue_inventory',return_value={'id':'job-1'} ) as enqueue, \
             patch('app.routers.rules.run_background_inventory_job') as run,TestClient(app) as client:
            response=client.post('/api/risk-knowledge/extractions',json={'policy_ids':[7,7,9]})
        self.assertEqual(response.status_code,200)
        enqueue.assert_called_once_with({'user_id':'manager','role':'relationship_manager'},[7,9])
        run.assert_called_once_with('job-1',{'user_id':'manager','role':'relationship_manager'})

    def test_empty_or_invalid_selection_never_extracts_all_documents(self):
        app=FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[routes.current_user]=lambda:{'user_id':'analyst','role':'credit_analyst'}
        with patch('app.routers.rules.enqueue_inventory') as enqueue,TestClient(app) as client:
            for payload in [{'policy_ids':[]},{'policy_ids':[0]},{'policy_ids':[-1]},{}]:
                self.assertEqual(client.post('/api/risk-knowledge/extractions',json=payload).status_code,422)
        enqueue.assert_not_called()

    def test_read_only_role_cannot_start_risk_knowledge_extraction(self):
        app=FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[routes.current_user]=lambda:{'user_id':'viewer','role':'viewer'}
        with patch('app.routers.rules.enqueue_inventory') as enqueue,TestClient(app) as client:
            self.assertEqual(client.post('/api/risk-knowledge/extractions',json={'policy_ids':[7]}).status_code,403)
        enqueue.assert_not_called()


if __name__=='__main__':unittest.main()
