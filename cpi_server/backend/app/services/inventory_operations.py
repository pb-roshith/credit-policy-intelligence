"""Discovery, persisted quality review and explicit human demo assessment operations."""
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from ..config import BASE_DIR, POLICY_OUTPUT_DIR, POLICY_SOURCE_DIR, MISTRAL_POLICY_MODEL, RULE_INVENTORY_WORKERS
from ..database import shared_policy_connection, db_connection
from ..agents.credit_policy_rule_quality_review import CreditPolicyRuleQualityReviewAgent

logger=logging.getLogger('credit_policy_intelligence.inventory')


def definition_checksum(definition):
    return hashlib.sha256(json.dumps(definition,sort_keys=True,default=str).encode()).hexdigest()


def discover_documents(register=False):
    with shared_policy_connection() as c:
        catalog=c.execute("SELECT policy_id,title,file_name,local_pdf_path,source_type,status FROM policy_documents ORDER BY policy_id").fetchall()
    by_name={row['file_name']:row for row in catalog}
    paths={}
    for directory in (POLICY_OUTPUT_DIR,POLICY_SOURCE_DIR):
        if directory.is_dir():
            for path in sorted(directory.rglob('*')):
                if path.is_file() and path.suffix.lower() in ('.pdf','.docx','.txt','.text'):paths[path.name]=path.resolve()
    for row in catalog:
        path=Path(row['local_pdf_path']).resolve()
        if path.is_file() and path.is_relative_to(BASE_DIR.resolve()):paths.setdefault(path.name,path)
    found=[]
    for name,path in sorted(paths.items()):
        row=by_name.get(name);error=None
        if register and row is None:
            # Local registration is explicit about unknown metadata and never operational.
            # Existing manufactured/imported documents already carry their catalog metadata.
            try:
                from .policy_ingestion import parse_document
                spans=parse_document(path);digest=hashlib.sha256(path.read_bytes()).hexdigest()
                with shared_policy_connection() as c:
                    c.execute("SELECT pg_advisory_xact_lock(hashtext('policy-local-registration'))")
                    sequence=c.execute('SELECT COALESCE(MAX(display_order),0)+1 AS n FROM policy_documents').fetchone()['n']
                    row=c.execute("""INSERT INTO policy_documents(policy_code,title,version,policy_category,parent_policy,clause_number,display_order,document_format,source_type,effective_date,status,summary,page_count,file_name,local_pdf_path,mistral_document_id,mistral_library_id,mistral_agent_id)
                        VALUES (%s,%s,'Unspecified','Unspecified','Unspecified','',%s,%s,%s,CURRENT_DATE,'Pending Metadata',%s,%s,%s,%s,%s,'local-registration','not-provisioned') RETURNING policy_id,title,file_name,local_pdf_path,source_type,status""",
                        ('LOCAL-'+digest[:24],path.stem,sequence,path.suffix[1:].upper(),'manufactured' if path.is_relative_to(POLICY_OUTPUT_DIR.resolve()) else 'imported',spans[0]['source_excerpt'],max((s['page_number'] or 1 for s in spans)),name,str(path),'local:'+digest)) .fetchone()
            except Exception as failure:error=type(failure).__name__
        item={'policy_id':row['policy_id'] if row else None,'title':row['title'] if row else path.stem,
            'file_name':name,'source_type':row['source_type'] if row else 'unregistered','path':str(path),
            'available':True,'registered':row is not None,'status':row['status'] if row else 'Registration required',
            'error':error,'retry_status':'Metadata review required' if row and row['status']=='Pending Metadata' else 'Retry registration' if error else None}
        found.append(item)
    for row in catalog:
        if row['file_name'] not in paths:
            found.append({**row,'path':row['local_pdf_path'],'available':False,'registered':True,'error':'Source file unavailable','retry_status':'Restore source and retry'})
    if register:
        for item in found:logger.info('Discovered policy document %s',json.dumps(item,default=str))
    return found


def review_batches(rows):
    batch=[];clauses={}
    for row in rows:
        rule={key:row[key] for key in ('id','policy_id','policy_version','version','rule_code','clause_id','definition')}
        clause={key:row[key] for key in ('clause_id','section_heading','clause_number','page_number','source_excerpt')}
        trial=batch+[rule];trial_clauses={**clauses,row['clause_id']:clause}
        if batch and (len(trial)>8 or len(json.dumps({'rules':trial,'source_clauses':list(trial_clauses.values()),'comparison_rules':[]},default=str))>45000):
            yield batch,list(clauses.values());batch=[];clauses={}
        batch.append(rule);clauses[row['clause_id']]=clause
    if batch:yield batch,list(clauses.values())


def run_quality_reviews(job_id,user):
    agent=CreditPolicyRuleQualityReviewAgent()
    with shared_policy_connection() as c:
        job=c.execute('SELECT policy_ids FROM rule_inventory_jobs WHERE id=%s',(job_id,)).fetchone()
        rows=c.execute("""SELECT r.*,e.rule_code,cl.section_heading,cl.clause_number,cl.page_number,cl.source_excerpt
          FROM policy_rule_versions r JOIN policy_rule_entities e ON e.id=r.rule_entity_id
          JOIN policy_versions pv ON pv.id=r.policy_version_id JOIN policy_clauses cl ON cl.id=r.clause_id
          WHERE credit_data.is_quantitative_rule(r.definition) AND r.policy_id=ANY(%s) AND pv.is_current
          AND (r.status IN ('Draft','Under Review') OR (r.status='Approved' AND EXISTS (
              SELECT 1 FROM risk_knowledge_objects evidence WHERE evidence.kind='metadata' AND evidence.owner_id=''
              AND evidence.id='CPI-RULE-'||r.id::text AND evidence.payload->>'job_id'=%s)))
          ORDER BY r.policy_id,r.clause_id,r.id""",(job['policy_ids'],str(job_id))).fetchall()
        cached=c.execute('SELECT * FROM rule_quality_reports WHERE prompt_version=%s',(agent.prompt_version,)).fetchall()
    complete={(r['rule_version_id'],r['definition_checksum']) for r in cached if r['status']=='Completed'}
    pending=[row for row in rows if (row['id'],definition_checksum(row['definition'])) not in complete]
    failed={(row['rule_version_id'],row['definition_checksum']):row for row in cached if row['status']=='Failed'}
    with shared_policy_connection() as c:
        for row in pending:
            previous=failed.get((row['id'],definition_checksum(row['definition'])))
            if previous:
                c.execute("INSERT INTO audit_events(entity_type,entity_id,previous_value,new_value,action,actor,reason) VALUES ('RuleQualityReport',%s,%s::jsonb,%s::jsonb,'QualityReviewRetry',%s,'Preserve failed quality report before retry')",(str(previous['id']),json.dumps(previous,default=str),json.dumps({'job_id':str(job_id),'rule_version_id':row['id'],'status':'Retry requested'}),user['user_id']))
    totals={'quality_candidates':len(rows),'quality_reviewed':len(rows)-len(pending),'quality_failed':0,'quality_pending':len(pending)}
    def progress():
        with shared_policy_connection() as c:c.execute('UPDATE rule_inventory_jobs SET review_progress=%s::jsonb,heartbeat_at=CURRENT_TIMESTAMP WHERE id=%s',(json.dumps(totals),job_id))
        logger.info('Inventory quality progress %s',json.dumps(totals))
    progress()
    def review(batch,clauses):
        execution_id=str(uuid4());failure=None
        with shared_policy_connection() as c:c.execute("INSERT INTO agent_execution_logs(id,job_id,agent_name,model_name,prompt_version,status,attempt) VALUES (%s,%s,%s,%s,%s,'Running',1)",(execution_id,job_id,agent.name,MISTRAL_POLICY_MODEL,agent.prompt_version))
        try:reports={item['rule_version_id']:item['report'] for item in agent.run_batch(batch,clauses)}
        except Exception as error:
            from pydantic import ValidationError
            reports={}
            failure=json.dumps([{'path':e['loc'],'type':e['type']} for e in error.errors(include_input=False,include_context=False)])[:2000] if isinstance(error,ValidationError) else str(error)[:1000] if isinstance(error,ValueError) else type(error).__name__
        with shared_policy_connection() as c:
            for rule in batch:
                report=reports.get(rule['id']);checksum=definition_checksum(rule['definition'])
                c.execute("""INSERT INTO rule_quality_reports(job_id,rule_version_id,definition_checksum,prompt_version,execution_id,status,report,error_code,retry_status)
                  VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT(rule_version_id,definition_checksum,prompt_version)
                  DO UPDATE SET job_id=EXCLUDED.job_id,execution_id=EXCLUDED.execution_id,status=EXCLUDED.status,report=EXCLUDED.report,error_code=EXCLUDED.error_code,retry_status=EXCLUDED.retry_status,created_at=CURRENT_TIMESTAMP""",
                  (job_id,rule['id'],checksum,agent.prompt_version,execution_id,'Completed' if report else 'Failed',json.dumps(report) if report else None,failure,'No retry needed' if report else 'Retry available'))
                if report:
                    c.execute("INSERT INTO audit_events(entity_type,entity_id,previous_value,new_value,action,actor,reason) VALUES ('PolicyRuleVersion',%s,%s::jsonb,%s::jsonb,'AdvisoryQualityReview',%s,'Inventory AI quality review; human governance unchanged')",(str(rule['id']),json.dumps({'definition':rule['definition']},default=str),json.dumps({'report':report,'execution_id':execution_id,'advisory_only':True}),user['user_id']))
                    for code in report['duplicate_candidates']:
                        other=next((r for r in batch if str(r['id'])==code),None)
                        if other and other['id']!=rule['id']:
                            c.execute("INSERT INTO rule_relationships(rule_version_id,related_rule_version_id,relationship_type,reason) VALUES (%s,%s,'Duplicate candidate','Quality Review Agent flagged a supplied comparison; human review required') ON CONFLICT DO NOTHING",(rule['id'],other['id']))
            c.execute('UPDATE agent_execution_logs SET status=%s,error_code=%s,finished_at=CURRENT_TIMESTAMP WHERE id=%s',('Failed' if failure else 'Completed',failure,execution_id))
        return len(reports),len(batch)-len(reports)
    with ThreadPoolExecutor(max_workers=RULE_INVENTORY_WORKERS,thread_name_prefix='inventory-quality') as pool:
        futures=[pool.submit(copy_context().run,review,batch,clauses) for batch,clauses in review_batches(pending)]
        for future in as_completed(futures):
            ok,failed=future.result();totals['quality_reviewed']+=ok;totals['quality_failed']+=failed;totals['quality_pending']-=ok+failed;progress()
    return totals


def exception_report(job_id):
    with shared_policy_connection() as c:
        job=c.execute('SELECT * FROM rule_inventory_jobs WHERE id=%s',(job_id,)).fetchone()
        if not job:raise ValueError('Inventory job not found')
        attempts=c.execute('SELECT * FROM inventory_batch_attempts WHERE job_id=%s ORDER BY id',(job_id,)).fetchall()
        logs=c.execute("SELECT id,policy_version_id,agent_name,attempt,error_code,started_at,finished_at FROM agent_execution_logs WHERE job_id=%s AND status='Failed' ORDER BY started_at",(job_id,)).fetchall()
        earlier=c.execute("SELECT log.id,log.job_id,log.policy_version_id,log.agent_name,log.attempt,log.error_code,log.started_at FROM agent_execution_logs log JOIN policy_versions pv ON pv.id=log.policy_version_id WHERE pv.policy_id=ANY(%s) AND log.status='Failed' AND log.job_id IS DISTINCT FROM %s::uuid ORDER BY log.started_at",(job['policy_ids'],job_id)).fetchall()
        retry_history=c.execute("SELECT id,entity_id,previous_value,new_value,actor,created_at FROM audit_events WHERE entity_type='RuleQualityReport' AND action='QualityReviewRetry' AND new_value->>'job_id'=%s ORDER BY id",(str(job_id),)).fetchall()
        active=c.execute("SELECT COUNT(*) AS n FROM policy_rule_versions WHERE credit_data.is_quantitative_rule(definition) AND policy_id=ANY(%s) AND status='Active' AND active AND approved_by IS NOT NULL",(job['policy_ids'],)).fetchone()['n']
        quality=c.execute("SELECT qr.*,e.rule_code,r.version,r.status AS rule_status FROM rule_quality_reports qr JOIN policy_rule_versions r ON r.id=qr.rule_version_id JOIN policy_rule_entities e ON e.id=r.rule_entity_id WHERE credit_data.is_quantitative_rule(r.definition) AND r.policy_id=ANY(%s) AND (qr.status='Failed' OR qr.report->>'review_result'<>'ACCEPTABLE_FOR_HUMAN_REVIEW') ORDER BY r.policy_id,r.id",(job['policy_ids'],)).fetchall()
        unresolved=c.execute("SELECT r.id,r.version,e.rule_code,r.policy_id,r.definition->'missing_information' AS missing_information,r.definition->'ambiguities' AS ambiguities FROM policy_rule_versions r JOIN policy_rule_entities e ON e.id=r.rule_entity_id WHERE credit_data.is_quantitative_rule(r.definition) AND r.policy_id=ANY(%s) AND (jsonb_array_length(COALESCE(r.definition->'missing_information','[]'))>0 OR jsonb_array_length(COALESCE(r.definition->'ambiguities','[]'))>0) ORDER BY r.id",(job['policy_ids'],)).fetchall()
    return {'job':job,'batch_attempts':attempts,'failed_agent_executions':logs,'historical_failed_agent_executions':earlier,'quality_retry_history':retry_history,'quality_exceptions':quality,'unresolved_rules':unresolved,
            'assessment_status':'Human-approved active inventory available for account-specific reassessment' if active else 'Awaiting explicit human approval and activation; historical findings preserved',
            'generated_at':datetime.now(timezone.utc).isoformat()}


def finalize_inventory_summary(job_id):
    """Refresh aggregate counters from persisted records, never manufacture rules."""
    with shared_policy_connection() as c:
        job=c.execute('SELECT * FROM rule_inventory_jobs WHERE id=%s',(job_id,)).fetchone()
        outcomes=c.execute("SELECT report->>'review_result' AS result,COUNT(*) AS n FROM rule_quality_reports qr JOIN policy_rule_versions r ON r.id=qr.rule_version_id WHERE credit_data.is_quantitative_rule(r.definition) AND r.policy_id=ANY(%s) AND qr.status='Completed' GROUP BY 1",(job['policy_ids'],)).fetchall()
        counters=c.execute("SELECT COUNT(*) AS rules_in_inventory,COUNT(*) FILTER (WHERE status='Draft') AS draft_rules,COUNT(*) FILTER (WHERE status='Active') AS active_rules FROM policy_rule_versions WHERE credit_data.is_quantitative_rule(definition) AND policy_id=ANY(%s)",(job['policy_ids'],)).fetchone()
        counters.update(c.execute("SELECT COUNT(*) AS duplicate_relationships_in_inventory FROM rule_relationships rel JOIN policy_rule_versions r ON r.id=rel.rule_version_id WHERE credit_data.is_quantitative_rule(r.definition) AND r.policy_id=ANY(%s) AND rel.relationship_type='Duplicate candidate'",(job['policy_ids'],)).fetchone())
        counters.update({'documents_discovered':len(job['discovered_documents']),
            'manufactured_documents':sum(d.get('source_type')=='manufactured' for d in job['discovered_documents']),
            'imported_documents':sum(d.get('source_type')=='imported' for d in job['discovered_documents']),
            'policies_reused':sum(p['status']=='Already processed' for p in job['progress'])})
        counters.update({'quality_'+r['result'].lower():r['n'] for r in outcomes})
        report={**job['report'],**counters}
        c.execute('UPDATE rule_inventory_jobs SET report=%s::jsonb WHERE id=%s',(json.dumps(report),job_id))
        return report


def assess_synthetic_requests(user):
    """User-authorized fresh runs in the caller's RLS scope; never rewrite old reviews."""
    from .rule_assessment import run_rule_assessment,active_rule_candidates
    if not active_rule_candidates(datetime.now(timezone.utc).date()):
        return {'status':'Awaiting human approval and activation','assessments':[],'failures':[]}
    with db_connection() as c:
        requests=c.execute("SELECT credit_request_number FROM credit_requests WHERE shared_deal_id IS NULL ORDER BY credit_request_number").fetchall()
    assessments=[];failures=[]
    for row in requests:
        request_id=row['credit_request_number']
        try:
            result=run_rule_assessment(request_id,user['user_id'],user=user)
            assessments.append({'request_id':request_id,'review_id':result['review_id'],'outcome_counts':result['outcome_counts']})
        except Exception as error:
            from fastapi import HTTPException
            failures.append({'request_id':request_id,'error':str(error.detail) if isinstance(error,HTTPException) else type(error).__name__,'retry_status':'Retry available'})
    return {'status':'Completed with errors' if failures else 'Completed','assessments':assessments,'failures':failures}
