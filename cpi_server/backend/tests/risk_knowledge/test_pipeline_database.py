"""Opt-in pipeline test against PostgreSQL. All fixture writes are rolled back."""
import os
from contextlib import contextmanager,ExitStack
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest
from unittest.mock import patch
import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException
from app.config import DATABASE_URL
from app.risk_knowledge.llm import MockLLMProvider
from app.risk_knowledge.pipeline import process_policy,PIPELINE_VERSION
from app.risk_knowledge.service import IntelligenceService
from app.risk_knowledge.repositories import PostgreSQLRepository
from app.services.inventory_schema import ExtractionOutput,GovernedDefinition,GovernedRuleInput
from app.services.rule_extraction import validate_extraction
from app.services.rule_governance import store_rule,change_status
from app.services.policy_ingestion import ingest_policy
from app.services.rule_assessment import active_rule_candidates
from test_inventory_pipeline import proposed


@unittest.skipUnless(os.getenv('RUN_RISK_KNOWLEDGE_DB_TESTS')=='1','Enable transactional Risk Knowledge pipeline test')
class PipelineDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.connection=psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=5)
        self.stack.callback(self.connection.close)
        self.stack.callback(self.connection.rollback)
        directory=self.stack.enter_context(TemporaryDirectory())
        source=Path(directory)/'selected-policy.txt'
        source.write_text('Exposure shall not exceed 100 USD.',encoding='utf-8')
        @contextmanager
        def shared():
            self.connection.execute('SET LOCAL search_path TO credit_data')
            yield self.connection
        self.shared=shared
        for module in ('policy_ingestion','rule_extraction','rule_governance','rule_assessment'):
            self.stack.enter_context(patch('app.services.'+module+'.shared_policy_connection',shared))
        self.stack.enter_context(patch('app.services.policy_ingestion.BASE_DIR',Path(directory)))
        self.stack.enter_context(patch('app.services.policy_ingestion.reconcile_policy_sources',lambda:None))
        self.actor={'user_id':'risk_knowledge_test_'+uuid4().hex[:12],'role':'credit_analyst'}
        code='TEST-RK-'+uuid4().hex
        with shared() as db:
            self.policy=db.execute("""INSERT INTO policy_documents(policy_code,title,version,policy_category,parent_policy,clause_number,display_order,effective_date,status,summary,page_count,file_name,local_pdf_path,mistral_document_id,mistral_library_id,mistral_agent_id,policy_type,source_type)
              VALUES (%s,'Risk Knowledge transactional fixture','1','Test','Test','1',31000,CURRENT_DATE,'Active','Exposure shall not exceed 100 USD.',1,%s,%s,%s,'test','test','Leverage','uploaded') RETURNING *""",(code,source.name,str(source),code)).fetchone()
        service=IntelligenceService(repository=PostgreSQLRepository(shared,self.actor['user_id']),data_dir=Path(directory)/'archive',provider=MockLLMProvider())
        self.service=service
        self.stack.enter_context(patch('app.risk_knowledge.pipeline.IntelligenceService',return_value=service))
        self.contexts=[]
        def extract(clauses,version_id,job=None,**kwargs):
            self.contexts.append(kwargs.get('knowledge_context'))
            clause=clauses[0]
            return validate_extraction(ExtractionOutput(rules=[proposed(clause_id=clause['id'],source_excerpt=clause['source_excerpt'])]),clauses)
        self.stack.enter_context(patch('app.services.rule_extraction.extract_batch',side_effect=extract))

    def test_partial_failure_and_same_job_retry_preserve_saved_groups(self):
        import hashlib,json
        from app.services.rule_extraction import PROMPT_VERSION,COMPATIBLE_CHECKPOINT_VERSIONS
        from app.services.extraction_failures import attach_failures
        source=Path(self.policy['local_pdf_path'])
        source.write_text(source.read_text()+'\n\nBorrower exposure shall not exceed 100 USD.',encoding='utf-8')
        job_id=str(uuid4())
        with self.shared() as db:
            db.execute("INSERT INTO rule_inventory_jobs(id,status,policy_ids,created_by,report) VALUES (%s,'Failed',%s::jsonb,%s,%s::jsonb)",
                       (job_id,json.dumps([self.policy['policy_id']]),self.actor['user_id'],json.dumps({'pipeline':PIPELINE_VERSION})))
        original_extract=__import__('app.services.rule_extraction',fromlist=['extract_batch']).extract_batch
        def fail_second(clauses,*args,**kwargs):
            if clauses[0]['sequence']==2:
                raise ValueError('Threshold is not explicitly present in its supporting excerpt')
            return original_extract(clauses,*args,**kwargs)
        with patch('app.services.rule_extraction.RULE_CLAUSE_BATCH_SIZE',1),patch('app.services.rule_extraction.extract_batch',side_effect=fail_second):
            first=process_policy(self.policy['policy_id'],self.actor,job_id)
        self.assertEqual(first['status'],'Completed with errors',first)
        self.assertTrue(first['partial_result'])
        self.assertEqual(first['failed_batches'],1)
        self.assertEqual(first['rules_proposed'],1)
        self.assertIn('1 of 2 clause groups failed',first['error'])
        self.assertEqual(next(s['status'] for s in first['stages'] if s['id']=='graph'),'Completed')
        with self.shared() as db:
            historical=attach_failures([{'id':job_id,'progress':[{'policy_id':self.policy['policy_id'],'status':'Failed','rules_proposed':1}]}],db)
            self.assertIn('Threshold is not explicitly',historical[0]['progress'][0]['error'])
            checkpoint=db.execute('SELECT * FROM rule_extraction_batches WHERE policy_version_id=%s',(first['policy_version_id'],)).fetchone()
            annotation=self.service.repo.get('metadata','CPI-RULE-'+str(checkpoint['rule_ids'][0]))
            clause_id=db.execute('SELECT clause_id FROM policy_rule_versions WHERE id=%s',(checkpoint['rule_ids'][0],)).fetchone()['clause_id']
            legacy_key=hashlib.sha256((str(first['policy_version_id'])+':'+str(clause_id)+':'+COMPATIBLE_CHECKPOINT_VERSIONS[0]+':'+annotation['context_fingerprint']+':'+job_id).encode()).hexdigest()
            db.execute('UPDATE rule_extraction_batches SET batch_key=%s WHERE id=%s',(legacy_key,checkpoint['id']))
        with patch('app.services.rule_extraction.RULE_CLAUSE_BATCH_SIZE',1):
            second=process_policy(self.policy['policy_id'],self.actor,job_id)
        self.assertEqual(second['status'],'Completed',second)
        self.assertEqual(second['validation_failures'],0)
        self.assertEqual(len(self.contexts),2) # One original group and only the previously failed group.
        with self.shared() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM policy_rule_versions WHERE policy_id=%s',(self.policy['policy_id'],)).fetchone()['n'],2)

    def test_vocabulary_change_does_not_duplicate_source_validated_extraction(self):
        from app.risk_knowledge.models import Concept,Provenance
        first=process_policy(self.policy['policy_id'],self.actor)
        with self.shared() as db:
            before=db.execute('SELECT id FROM policy_rule_versions WHERE policy_id=%s ORDER BY id',(self.policy['policy_id'],)).fetchall()
        added=Concept(concept_id='test-new-vocabulary-'+uuid4().hex,preferred_name='New schema vocabulary',status='APPROVED',
            source=Provenance(document_id='schema-test',document_name='Schema.xlsx',origin='SOURCE_SCHEMA',passage='New schema vocabulary'))
        self.service.repo.put('taxonomy_concepts',added.concept_id,added.model_dump())
        second=process_policy(self.policy['policy_id'],self.actor)
        self.assertEqual(first['status'],'Completed')
        self.assertEqual(second['status'],'Completed')
        self.assertEqual(len(self.contexts),1)
        with self.shared() as db:
            self.assertEqual(db.execute('SELECT id FROM policy_rule_versions WHERE policy_id=%s ORDER BY id',(self.policy['policy_id'],)).fetchall(),before)

    def test_auto_approved_rules_still_receive_job_quality_review(self):
        import json
        from app.services.inventory_operations import run_quality_reviews
        job_id=str(uuid4())
        with self.shared() as db:
            db.execute("INSERT INTO rule_inventory_jobs(id,status,policy_ids,created_by,report) VALUES (%s,'Failed',%s::jsonb,%s,%s::jsonb)",
                       (job_id,json.dumps([self.policy['policy_id']]),self.actor['user_id'],json.dumps({'pipeline':PIPELINE_VERSION})))
        result=process_policy(self.policy['policy_id'],self.actor,job_id)
        self.assertEqual(result['rules_approved'],1)
        with self.shared() as db:
            row=db.execute('SELECT id,status FROM policy_rule_versions WHERE policy_id=%s',(self.policy['policy_id'],)).fetchone()
        self.assertEqual(row['status'],'Approved')
        with patch('app.services.inventory_operations.shared_policy_connection',self.shared), \
             patch('app.services.inventory_operations.CreditPolicyRuleQualityReviewAgent') as agent:
            agent.return_value.prompt_version='pipeline-quality-test-v1'
            agent.return_value.name='Quality review fixture'
            agent.return_value.run_batch.return_value=[{'rule_version_id':row['id'],'report':{
                'review_result':'ACCEPTABLE_FOR_HUMAN_REVIEW','duplicate_candidates':[]}}]
            quality=run_quality_reviews(job_id,self.actor)
        self.assertEqual(quality['quality_candidates'],1)
        self.assertEqual(quality['quality_reviewed'],1)
        self.assertEqual(quality['quality_failed'],0)

    def test_automatic_approval_is_audited_idempotent_and_rejects_invented_limits(self):
        from app.services.automatic_approval import approve_rules
        policy,version,doc,clauses=ingest_policy(self.policy['policy_id'])
        rows=[]
        for sequence,value in ((1,100),(2,1000)):
            definition=GovernedDefinition(**proposed(clause_id=clauses[0]['id'],rule_sequence=sequence,threshold_value=value),change_rationale='Source validation fixture')
            rows.append(store_rule(GovernedRuleInput(policy_id=policy['policy_id'],definition=definition,effective_from=date.today()),self.actor,extraction_key='risk-knowledge:test:'+uuid4().hex,force_draft=True))
        ids=[row['id'] for row in rows]
        self.assertEqual(approve_rules(self.shared,ids),[ids[0]])
        self.assertEqual(approve_rules(self.shared,ids),[])
        with self.shared() as db:
            self.assertEqual(db.execute('SELECT status FROM policy_rule_versions WHERE id=%s',(ids[1],)).fetchone()['status'],'Draft')
            reviews=db.execute('SELECT reviewed_by,decision FROM rule_reviews WHERE rule_version_id=%s',(ids[0],)).fetchall()
            self.assertEqual(reviews,[{'reviewed_by':'system:auto-approval','decision':'approve'}])

    def test_old_rule_cleanup_preserves_new_rules_and_writes_recoverable_backup(self):
        import json
        from app.services.automatic_approval import approve_rules
        from app.services.extraction_cleanup import remove_old_extracted_rules
        policy,version,doc,clauses=ingest_policy(self.policy['policy_id'])
        definition=GovernedDefinition(**proposed(clause_id=clauses[0]['id']),change_rationale='Cleanup fixture')
        payload=GovernedRuleInput(policy_id=policy['policy_id'],definition=definition,effective_from=date.today())
        old=store_rule(payload,self.actor,extraction_key='legacy-fixture-'+uuid4().hex)
        new=store_rule(payload,self.actor,previous=old['id'],extraction_key='risk-knowledge:test:'+uuid4().hex,force_draft=True)
        approve_rules(self.shared,[new['id']])
        self.service.repo.put('metadata','CPI-RULE-'+str(new['id']),{'taxonomy_mappings':[{'status':'RESOLVED','concept_id':'fixture-exposure'}]})
        with TemporaryDirectory() as backup:
            result=remove_old_extracted_rules(self.shared,backup,old_rule_ids=[old['id']])
            self.assertEqual(result['removed'],1)
            saved=json.loads(Path(result['backup']).read_text(encoding='utf-8'))
            self.assertEqual(saved['policy_rule_versions'][0]['id'],old['id'])
            self.assertTrue(saved['dependent_tables']['policy_rule_audit'])
        with self.shared() as db:
            self.assertIsNone(db.execute('SELECT id FROM policy_rule_versions WHERE id=%s',(old['id'],)).fetchone())
            kept=db.execute('SELECT * FROM policy_rule_versions WHERE id=%s',(new['id'],)).fetchone()
            self.assertEqual(kept['status'],'Approved')
            self.assertIsNone(kept['superseded_version_id'])

    def test_enrichment_keeps_existing_rule_ids_without_extracting_again(self):
        from app.risk_knowledge.enrichment import enrich_saved_policy
        report=process_policy(self.policy['policy_id'],self.actor)
        with self.shared() as db:
            before=db.execute('SELECT id FROM policy_rule_versions WHERE policy_id=%s ORDER BY id',(self.policy['policy_id'],)).fetchall()
        with patch('app.services.rule_extraction.extract_batch',side_effect=AssertionError('Enrichment must not extract new rules')):
            result=enrich_saved_policy(self.policy['policy_id'],self.actor,self.shared,provider=MockLLMProvider())
        self.assertEqual(result['rules_created'],0)
        self.assertEqual(result['rules_mapped'],1)
        with self.shared() as db:
            self.assertEqual(db.execute('SELECT id FROM policy_rule_versions WHERE policy_id=%s ORDER BY id',(self.policy['policy_id'],)).fetchall(),before)

    def test_selected_policy_to_library_graph_retry_and_review(self):
        policy,version,doc,clauses=ingest_policy(self.policy['policy_id'])
        definition=GovernedDefinition(**proposed(clause_id=clauses[0]['id']),change_rationale='Pre-existing legacy rule fixture')
        legacy=store_rule(GovernedRuleInput(policy_id=policy['policy_id'],definition=definition,effective_from=date.today()),self.actor,extraction_key='legacy-fixture-'+uuid4().hex)
        self.assertEqual(legacy['status'],'Active')
        report=process_policy(policy['policy_id'],self.actor)
        self.assertEqual(report['status'],'Completed',report)
        self.assertEqual(report['pipeline'],PIPELINE_VERSION)
        self.assertEqual(report['rules_proposed'],1)
        self.assertTrue(all(stage['status']=='Completed' for stage in report['stages']))
        self.assertTrue(self.contexts[0]['source_schema'])
        with self.shared() as db:
            draft=db.execute('SELECT * FROM policy_rule_versions WHERE policy_id=%s ORDER BY version DESC LIMIT 1',(policy['policy_id'],)).fetchone()
        self.assertEqual(draft['status'],'Approved')
        self.assertEqual(draft['approved_by'],'system:auto-approval')
        self.assertFalse(draft['active'])
        self.assertEqual(draft['version'],legacy['version']+1)
        evidence=self.service.repo.get('metadata','CPI-RULE-'+str(draft['id']))
        self.assertEqual(evidence['source']['passage'],'Exposure shall not exceed 100 USD.')
        self.assertTrue(evidence['validation']['source_provenance_verified'])
        self.assertIn('CPI-RULE-'+str(draft['id']),self.service.graph.nodes)
        self.assertTrue(any(edge['source']=='CPI-RULE-'+str(draft['id']) and edge['predicate']=='DERIVED_FROM' for edge in self.service.graph.edges))
        eligible={row['id'] for row in active_rule_candidates(date.today())}
        self.assertNotIn(legacy['id'],eligible)
        self.assertIn(draft['id'],eligible)
        second=process_policy(policy['policy_id'],self.actor)
        self.assertEqual(second['status'],'Completed')
        self.assertEqual(len(self.contexts),1) # Retry reused the source/context checkpoint.
        with self.shared() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM policy_rule_versions WHERE policy_id=%s',(policy['policy_id'],)).fetchone()['n'],2)
            migration=Path(__file__).resolve().parents[2]/'app/migrations/004_rules_available_by_default.sql'
            db.execute(migration.read_text(encoding='utf-8-sig'))
            self.assertEqual(db.execute('SELECT status FROM policy_rule_versions WHERE id=%s',(draft['id'],)).fetchone()['status'],'Approved')
        reviewed_definition=GovernedDefinition.model_validate({**draft['definition'],'data_source':'Reviewed exposure input','severity':'BREACH','change_rationale':'Human verified input source and operational severity'})
        revision=store_rule(GovernedRuleInput(policy_id=policy['policy_id'],definition=reviewed_definition,effective_from=date.today()),self.actor,previous=draft['id'])
        self.assertEqual(revision['status'],'Draft')
        approved=change_status(revision['id'],'submit','Verified source and input mapping',self.actor)
        self.assertEqual(approved['status'],'Approved')
        self.assertEqual(approved['approved_by'],'system:auto-approval')
        self.assertFalse(approved['active'])
        with self.assertRaises(HTTPException):
            change_status(revision['id'],'activate','Attempt overlapping activation',self.actor)
        change_status(legacy['id'],'deactivate','Reviewed replacement is ready',self.actor)
        activated=change_status(revision['id'],'activate','Activate reviewed replacement',self.actor)
        self.assertTrue(activated['active'])
        eligible={row['id'] for row in active_rule_candidates(date.today())}
        self.assertIn(activated['id'],eligible)
        self.assertNotIn(legacy['id'],eligible)
        with self.shared() as db:
            db.execute(migration.read_text(encoding='utf-8-sig'))
            self.assertFalse(db.execute('SELECT active FROM policy_rule_versions WHERE id=%s',(legacy['id'],)).fetchone()['active'])
