"""Explicit PostgreSQL integration tests; all fixture data rolls back."""
import os
import unittest
from contextlib import contextmanager,ExitStack
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from unittest.mock import patch
import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException
from app.config import DATABASE_URL
from app.services.inventory_schema import ExtractionOutput,GovernedRuleInput,GovernedDefinition
from app.services.rule_extraction import process_policy,validate_extraction
from app.services.rule_governance import store_rule,change_status
from app.services.rule_assessment import run_rule_assessment
from test_inventory_pipeline import proposed

@unittest.skipUnless(os.getenv('RUN_INVENTORY_DB_TESTS')=='1','Enable explicit transactional PostgreSQL tests')
class InventoryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection=psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=5)
        self.stack=ExitStack();self.stack.callback(self.connection.close);self.stack.callback(self.connection.rollback)
        self.directory=self.stack.enter_context(TemporaryDirectory())
        self.actor={'user_id':'inventory_test_'+uuid4().hex[:12],'role':'credit_analyst'}
        self.path=Path(self.directory)/'policy.txt';self.path.write_text('Exposure shall not exceed 100 USD.',encoding='utf-8')
        self.connection.execute("SET LOCAL search_path TO credit_data")
        code='TEST-'+uuid4().hex
        self.policy=self.connection.execute("""INSERT INTO policy_documents(policy_code,title,version,policy_category,parent_policy,clause_number,display_order,effective_date,status,summary,page_count,file_name,local_pdf_path,mistral_document_id,mistral_library_id,mistral_agent_id,policy_type,source_type)
          VALUES (%s,'Test Policy','1','Test','Test','1',31000,CURRENT_DATE,'Active','Exposure shall not exceed 100 USD.',1,%s,%s,%s,'test','test','Leverage','manufactured') RETURNING *""",(code,code+'.txt',str(self.path),code)).fetchone()
        @contextmanager
        def shared():
            self.connection.execute('SET LOCAL ROLE NONE');self.connection.execute('SET LOCAL search_path TO credit_data')
            yield self.connection
            self.connection.execute('SET LOCAL ROLE NONE');self.connection.execute('SET LOCAL search_path TO credit_data')
        @contextmanager
        def account():
            self.connection.execute("SELECT set_config('app.user_id',%s,true)",(self.actor['user_id'],))
            self.connection.execute('SET LOCAL ROLE credit_user_runtime');self.connection.execute('SET LOCAL search_path TO "user"')
            try:yield self.connection
            finally:self.connection.execute('SET LOCAL ROLE NONE');self.connection.execute('SET LOCAL search_path TO credit_data')
        for module in ('policy_ingestion','rule_extraction','rule_governance','rule_assessment'):
            self.stack.enter_context(patch(f'app.services.{module}.shared_policy_connection',shared))
        self.stack.enter_context(patch('app.services.policy_ingestion.BASE_DIR',Path(self.directory)))
        self.stack.enter_context(patch('app.services.rule_assessment.run_db_transaction',lambda operation: self.run_account(operation,account)))
        def extract(clauses,version,job=None):
            cl=clauses[0]
            output=ExtractionOutput.model_validate({'rules':[proposed(clause_id=cl['id'],source_excerpt=cl['source_excerpt'])]})
            return validate_extraction(output,clauses)
        self.stack.enter_context(patch('app.services.rule_extraction.extract_batch',extract))
        self.stack.enter_context(patch('app.services.assessment_request.deal_assessment_context',lambda request,user:{'credit_request_number':request,'borrower_name':'Fixture borrower','exposure':75,'currency':'USD','requested_amount':50,'status':'Pending','facility':'Term Loan','rating':'A'}))
        self.account=account
    def tearDown(self):self.stack.close()
    @staticmethod
    def run_account(operation,account):
        with account() as c:return operation(c)
    def draft(self):
        report=process_policy(self.policy['policy_id'],self.actor)
        self.assertEqual(report['rules_proposed'],1)
        return self.connection.execute('SELECT * FROM policy_rule_versions WHERE policy_id=%s',(self.policy['policy_id'],)).fetchone()
    def approve(self,row):
        d={**row['definition'],'severity':'BREACH','data_source':'Credit Dossier exposure','change_rationale':'Reviewer verified source and configured data field'}
        payload=GovernedRuleInput(policy_id=row['policy_id'],definition=GovernedDefinition.model_validate(d),effective_from=date.today())
        row=store_rule(payload,self.actor,previous=row['id'])
        change_status(row['id'],'submit','Ready for business review',self.actor)
        row=change_status(row['id'],'approve','Requirement and data mapping verified',self.actor)
        self.assertEqual(row['status'],'Approved');self.assertFalse(row['active'])
        return row
    def test_end_to_end_document_to_explainable_finding(self):
        row=self.draft();self.assertEqual(row['status'],'Draft');self.assertFalse(row['active'])
        row=self.approve(row);change_status(row['id'],'activate','Effective for production assessment',self.actor)
        result=run_rule_assessment('deal_fixture',self.actor['user_id'],user=self.actor)
        finding=next(f for f in result['findings'] if f['rule_version_id']==row['id'])
        self.assertEqual(finding['result'],'Pass');self.assertEqual(finding['observed_value'],75)
        self.assertIn('Test Policy',finding['explanation']);self.assertIn('version 1',finding['explanation'])
        with self.account() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM policy_request_mappings').fetchone()['n'],1)
            self.assertGreaterEqual(c.execute('SELECT COUNT(*) AS n FROM assessment_evidence').fetchone()['n'],2)
            stored=c.execute('SELECT * FROM request_rule_assessments').fetchone()
            self.assertEqual(stored['rule_version_id'],row['id'])
        events=self.connection.execute('SELECT action,previous_value,new_value FROM audit_events WHERE entity_id=%s ORDER BY id',(str(row['id']),)).fetchall()
        self.assertEqual([e['action'] for e in events],['extract draft','edit','submit','approve','activate'])
        self.assertIsNotNone(events[1]['previous_value'])
    def test_business_agent_contract_creates_only_governed_drafts(self):
        from app.services.policy_ingestion import ingest_policy
        from app.services.credit_policy_extraction_schema import CreditPolicyExtractionReport
        from app.services.credit_policy_extraction_adapter import to_inventory
        from app.agents.credit_policy_rule_extraction import validate_report
        from app.services.rule_extraction import process_policy
        policy,version,doc,clauses=ingest_policy(self.policy['policy_id'])
        cl=clauses[0]
        metadata=dict(policy_id=str(policy['policy_id']),policy_version=version['version'],source_document_id=str(doc['id']),extraction_run_id=str(uuid4()))
        public=CreditPolicyExtractionReport.model_validate({**metadata,'rules':[dict(proposed_rule_code=f"POL-{policy['policy_id']}-C{cl['sequence']}-R1",rule_name='Exposure limit',rule_description='Exposure shall not exceed 100 USD.',requirement_category='QUANTITATIVE',mandatory=True,source_section=cl['section_heading'],source_clause=cl['clause_number'] or f"un-numbered span {cl['sequence']}",source_page=cl['page_number'],source_excerpt=cl['source_excerpt'],check_question='Is exposure within 100 USD?',metric_name='exposure',operator='LTE',threshold_value=100,threshold_unit='USD',threshold_type='HARD_LIMIT',calculation_logic='exposure',input_data_fields=[dict(field_name='exposure',unit='USD',required=True)],extraction_confidence=0.9)]})
        internal=to_inventory(validate_report(public,metadata,clauses),clauses)
        with patch('app.services.rule_extraction.extract_batch',return_value=internal):
            report=process_policy(policy['policy_id'],self.actor)
        self.assertEqual(report['rules_proposed'],1)
        row=self.connection.execute('SELECT * FROM policy_rule_versions WHERE policy_id=%s',(policy['policy_id'],)).fetchone()
        self.assertEqual(row['status'],'Draft');self.assertFalse(row['active'])
        self.assertEqual(row['definition']['source_rule_code'],public.rules[0].proposed_rule_code)
        self.assertIsNone(row['definition']['severity'])
        self.assertEqual(row['definition']['threshold_type'],'HARD_LIMIT')
        field=self.connection.execute("SELECT field_unit FROM rule_input_requirements WHERE rule_version_id=%s AND field_name='exposure'",(row['id'],)).fetchone()
        self.assertEqual(field['field_unit'],'USD')

    def test_duplicate_ingestion_and_retry(self):
        self.draft();again=process_policy(self.policy['policy_id'],self.actor)
        self.assertEqual(again['status'],'Already processed')
        self.assertEqual(self.connection.execute('SELECT COUNT(*) AS n FROM policy_rule_versions WHERE policy_id=%s',(self.policy['policy_id'],)).fetchone()['n'],1)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) AS n FROM policy_versions WHERE policy_id=%s',(self.policy['policy_id'],)).fetchone()['n'],1)
    def test_activation_authorization_and_deactivation(self):
        row=self.approve(self.draft())
        with self.assertRaises(HTTPException) as error:change_status(row['id'],'activate','Denied',{'role':'relationship_manager','user_id':'other'})
        self.assertEqual(error.exception.status_code,403)
        change_status(row['id'],'activate','Enable check',self.actor)
        inactive=change_status(row['id'],'deactivate','Suspend check',self.actor)
        self.assertEqual(inactive['status'],'Inactive');self.assertFalse(inactive['active'])
    def test_version_changes_do_not_mutate_historical_assessment(self):
        row=self.approve(self.draft());change_status(row['id'],'activate','Enable check',self.actor)
        original=run_rule_assessment('deal_fixture',self.actor['user_id'],user=self.actor)
        definition={**row['definition'],'threshold_value':80,'threshold_source':None,'severity':'BREACH','data_source':'Credit Dossier exposure','change_rationale':'Human revised operational threshold'}
        new=store_rule(GovernedRuleInput(policy_id=row['policy_id'],definition=GovernedDefinition.model_validate(definition),effective_from=date.today()),self.actor,previous=row['id'])
        self.assertEqual(new['version'],2);self.assertEqual(new['superseded_version_id'],row['id']);self.assertEqual(new['status'],'Draft')
        with self.account() as c:
            stored=c.execute('SELECT review FROM ai_compliance_reviews WHERE review_id=%s',(original['review_id'],)).fetchone()['review']
        self.assertEqual(stored['findings'][0]['rule_version'],1);self.assertEqual(stored['findings'][0]['expected_threshold'],100)
    def test_incomplete_proposal_cannot_be_approved(self):
        row=self.draft()
        change_status(row['id'],'submit','Review ambiguous source mapping',self.actor)
        with self.assertRaises(HTTPException) as error:
            change_status(row['id'],'approve','Attempt premature approval',self.actor)
        self.assertEqual(error.exception.status_code,409)
        stored=self.connection.execute('SELECT status,active FROM policy_rule_versions WHERE id=%s',(row['id'],)).fetchone()
        self.assertEqual(stored['status'],'Under Review');self.assertFalse(stored['active'])

    def test_overlapping_active_versions_are_prevented(self):
        row=self.approve(self.draft());change_status(row['id'],'activate','Enable original',self.actor)
        d={**row['definition'],'severity':'BREACH','data_source':'Credit Dossier exposure','change_rationale':'Revised rule check description'}
        next_rule=store_rule(GovernedRuleInput(policy_id=row['policy_id'],definition=GovernedDefinition.model_validate(d),effective_from=date.today()),self.actor,previous=row['id'])
        change_status(next_rule['id'],'submit','Review new version',self.actor)
        change_status(next_rule['id'],'approve','Approve new version',self.actor)
        with self.assertRaises(HTTPException) as error:
            change_status(next_rule['id'],'activate','Attempt overlap',self.actor)
        self.assertEqual(error.exception.status_code,409)
        change_status(row['id'],'deactivate','Superseded',self.actor)
        updated=change_status(next_rule['id'],'activate','Activate replacement',self.actor)
        self.assertEqual(updated['status'],'Active')

    def test_policy_file_change_invalidates_old_source_and_preserves_archive(self):
        from app.services.policy_ingestion import reconcile_policy_sources,ingest_policy
        row=self.draft()
        original=self.connection.execute('SELECT source_path FROM inventory_documents WHERE policy_version_id=%s',(row['policy_version_id'],)).fetchone()
        self.path.write_text('Exposure shall not exceed 200 USD.',encoding='utf-8')
        reconcile_policy_sources()
        old=self.connection.execute('SELECT is_current FROM policy_versions WHERE id=%s',(row['policy_version_id'],)).fetchone()
        self.assertFalse(old['is_current'])
        self.assertEqual(Path(original['source_path']).read_text(encoding='utf-8'),'Exposure shall not exceed 100 USD.')
        _,version,_,_=ingest_policy(self.policy['policy_id'])
        self.assertNotEqual(version['id'],row['policy_version_id'])
        self.assertEqual(self.connection.execute('SELECT COUNT(*) AS n FROM policy_versions WHERE policy_id=%s',(self.policy['policy_id'],)).fetchone()['n'],2)

    def test_account_isolation(self):
        row=self.approve(self.draft());change_status(row['id'],'activate','Enable check',self.actor)
        run_rule_assessment('deal_fixture',self.actor['user_id'],user=self.actor)
        self.actor['user_id']='other_inventory_owner'
        with self.account() as c:self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM request_rule_assessments').fetchone()['n'],0)

    def test_quality_review_is_audited_without_approval_or_activation(self):
        from app.routers import rules
        row=self.draft()
        report={'review_result':'REVISION_REQUIRED','issues':['Operational mapping needs business review'],
            'unsupported_fields':[],'missing_fields':['data_source'],'duplicate_candidates':[],
            'recommended_revision':'Confirm the mapping','confidence':.9}
        from contextlib import contextmanager
        @contextmanager
        def shared():
            self.connection.execute('SET LOCAL search_path TO credit_data')
            yield self.connection
        with patch.object(rules,'shared_policy_connection',shared),patch('app.agents.credit_policy_rule_quality_review.CreditPolicyRuleQualityReviewAgent.run',return_value=report):
            output=rules.quality_review(row['id'],self.actor)
        after=self.connection.execute('SELECT * FROM policy_rule_versions WHERE id=%s',(row['id'],)).fetchone()
        self.assertEqual(after['status'],'Draft');self.assertFalse(after['active']);self.assertIsNone(after['approved_by'])
        self.assertTrue(output['advisory_only'])
        event=self.connection.execute("SELECT * FROM audit_events WHERE entity_id=%s AND action='AdvisoryQualityReview'",(str(row['id']),)).fetchone()
        self.assertEqual(event['new_value']['report'],report)
        self.assertEqual(event['previous_value']['definition'],row['definition'])

    def test_standalone_applicability_does_not_run_or_store_compliance(self):
        from app.routers.compliance import check_applicability
        from app.schemas import ComplianceReviewRequest
        row=self.approve(self.draft());change_status(row['id'],'activate','Enable check',self.actor)
        with patch('app.services.rule_engine.execute_rule',side_effect=AssertionError('Compliance must not run')):
            report=check_applicability(ComplianceReviewRequest(credit_request_number='deal_fixture'),self.actor)
        self.assertEqual(report['request_id'],'deal_fixture')
        self.assertTrue(any(d['candidate_type']=='Policy' for d in report['decisions']))
        self.assertTrue(all('result' not in d for d in report['decisions']))
        with self.account() as c:self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM rule_assessment_runs').fetchone()['n'],0)

    def test_failed_group_does_not_discard_other_groups_and_retry_is_checkpointed(self):
        from app.services.inventory_schema import ExtractionOutput
        self.path.write_text('Exposure shall not exceed 100 USD.\n\nFacility exposure shall not exceed 100 USD.',encoding='utf-8')
        def extract(clauses,version,job=None):
            clause=clauses[0]
            if clause['sequence']==1:raise ValueError('Rule extraction failed: test schema validation')
            return ExtractionOutput.model_validate({'rules':[proposed(clause_id=clause['id'],source_excerpt=clause['source_excerpt'])]})
        with patch('app.services.rule_extraction.RULE_CLAUSE_BATCH_SIZE',1),patch('app.services.rule_extraction.extract_batch',extract):
            report=process_policy(self.policy['policy_id'],self.actor)
        self.assertEqual(report['failed_batches'],1);self.assertEqual(report['clauses_processed'],1)
        self.assertEqual(report['rules_proposed'],1)
        attempt=self.connection.execute('SELECT * FROM inventory_batch_attempts WHERE policy_version_id IN (SELECT id FROM policy_versions WHERE policy_id=%s)',(self.policy['policy_id'],)).fetchone()
        self.assertEqual(attempt['retry_status'],'Retry available')
        with patch('app.services.rule_extraction.RULE_CLAUSE_BATCH_SIZE',1):
            report=process_policy(self.policy['policy_id'],self.actor)
        self.assertEqual(report['status'],'Completed')
        self.assertEqual(self.connection.execute('SELECT retry_status FROM inventory_batch_attempts WHERE id=%s',(attempt['id'],)).fetchone()['retry_status'],'Resolved by retry')
        self.assertEqual(self.connection.execute('SELECT COUNT(*) AS n FROM policy_rule_versions WHERE policy_id=%s',(self.policy['policy_id'],)).fetchone()['n'],2)

    def test_business_approval_cannot_add_a_missing_numeric_limit(self):
        row=self.draft();definition={**row['definition'],'threshold_value':999,'change_rationale':'Unstated example threshold'}
        payload=GovernedRuleInput(policy_id=row['policy_id'],definition=GovernedDefinition.model_validate(definition),effective_from=date.today())
        row=store_rule(payload,self.actor,previous=row['id']);change_status(row['id'],'submit','Review required',self.actor)
        with self.assertRaises(HTTPException) as error:change_status(row['id'],'approve','Approve',self.actor)
        self.assertEqual(error.exception.status_code,409)

    def test_quality_reports_are_persisted_cached_and_stale_after_edit(self):
        from app.services.inventory_operations import run_quality_reviews
        row=self.draft()
        job_id=str(uuid4())
        self.connection.execute("INSERT INTO rule_inventory_jobs(id,status,policy_ids,created_by) VALUES (%s,'Completed',%s::jsonb,%s)",(job_id,'['+str(row['policy_id'])+']',self.actor['user_id']))
        @contextmanager
        def shared():
            self.connection.execute('SET LOCAL search_path TO credit_data');yield self.connection
        def reviews(batch,clauses):
            return [{'rule_version_id':r['id'],'report':{'review_result':'UNSUPPORTED','issues':['Source needs review'],'unsupported_fields':['metric_name'],'missing_fields':[],'duplicate_candidates':[],'recommended_revision':'Confirm source mapping','confidence':.8}} for r in batch]
        with patch('app.services.inventory_operations.shared_policy_connection',shared),patch('app.agents.credit_policy_rule_quality_review.CreditPolicyRuleQualityReviewAgent.run_batch',side_effect=reviews) as model:
            totals=run_quality_reviews(job_id,self.actor)
            self.assertEqual(totals['quality_reviewed'],1);self.assertEqual(totals['quality_failed'],0)
            run_quality_reviews(job_id,self.actor);self.assertEqual(model.call_count,1)
            self.connection.execute("UPDATE policy_rule_versions SET definition=jsonb_set(definition,'{rule_name}','\"Revised name\"') WHERE id=%s",(row['id'],))
            run_quality_reviews(job_id,self.actor);self.assertEqual(model.call_count,2)
        after=self.connection.execute('SELECT status,active FROM policy_rule_versions WHERE id=%s',(row['id'],)).fetchone()
        self.assertEqual(after,{'status':'Draft','active':False})
        self.assertEqual(self.connection.execute('SELECT COUNT(*) AS n FROM rule_quality_reports WHERE rule_version_id=%s',(row['id'],)).fetchone()['n'],2)

    def test_discovery_registers_unknown_source_as_pending_metadata_without_rules(self):
        from app.services.inventory_operations import discover_documents
        unknown=Path(self.directory)/(uuid4().hex+'.txt');unknown.write_text('Supporting policy background only.',encoding='utf-8')
        @contextmanager
        def shared():
            self.connection.execute('SET LOCAL search_path TO credit_data');yield self.connection
        with patch('app.services.inventory_operations.shared_policy_connection',shared),patch('app.services.inventory_operations.BASE_DIR',Path(self.directory)),patch('app.services.inventory_operations.POLICY_OUTPUT_DIR',Path(self.directory)),patch('app.services.inventory_operations.POLICY_SOURCE_DIR',Path(self.directory)/'absent'):
            discovered=discover_documents(register=True)
        record=next(d for d in discovered if d['file_name']==unknown.name)
        self.assertTrue(record['registered']);self.assertEqual(record['status'],'Pending Metadata')
        self.assertEqual(self.connection.execute('SELECT COUNT(*) AS n FROM policy_rule_versions WHERE policy_id=%s',(record['policy_id'],)).fetchone()['n'],0)

if __name__=='__main__':unittest.main()
