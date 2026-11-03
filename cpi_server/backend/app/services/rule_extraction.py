"""Mistral extraction uses typed structured output and exact-source validation."""
import hashlib
import json
import logging
import re
import time
from contextvars import copy_context
from datetime import date
from difflib import SequenceMatcher
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
from mistralai.client import Mistral
from mistralai.client.utils.retries import RetryConfig, BackoffStrategy
from ..config import MISTRAL_API_KEY, MISTRAL_POLICY_MODEL, MISTRAL_TIMEOUT_MS, RULE_EXTRACTION_RETRIES, RULE_CLAUSE_BATCH_SIZE, RULE_INVENTORY_WORKERS
from ..database import shared_policy_connection
from ..telemetry import account_ai_job
from .inventory_schema import ExtractionOutput, GovernedRuleInput, GovernedDefinition
from .policy_ingestion import ingest_policy
from .rule_governance import store_rule

from ..agents.credit_policy_rule_extraction import CreditPolicyRuleExtractionAgent,SourceValidationError,SYSTEM_PROMPT,PROMPT_VERSION,COMPATIBLE_CHECKPOINT_VERSIONS
from .source_quantities import restore_stated_amount_units
from .credit_policy_extraction_adapter import to_inventory

logger=logging.getLogger('credit_policy_intelligence.inventory')

class ExtractionValidationError(SourceValidationError):
    pass


def validate_extraction(output,clauses):
    by_id={c['id']:c for c in clauses};seen=set()
    for rule in output.rules:
        if rule.clause_id not in by_id:raise ExtractionValidationError('Unknown source clause')
        key=(rule.clause_id,rule.rule_sequence)
        if key in seen:raise ExtractionValidationError('Duplicate atomic rule sequence')
        seen.add(key)
        source=by_id[rule.clause_id]['source_excerpt']
        if rule.source_excerpt not in source:
            # PDF line wrapping is not policy content. Restore the exact source
            # span when the only difference is whitespace; reject paraphrases.
            pattern=r'\s+'.join(re.escape(word) for word in rule.source_excerpt.split())
            match=re.search(pattern,source) if pattern else None
            if not match:raise ExtractionValidationError('Excerpt must match source exactly')
            rule.source_excerpt=match.group(0)
        restore_stated_amount_units(rule,rule.source_excerpt)
        if rule.threshold_source and rule.threshold_source not in source:
            match=re.search(r'\s+'.join(re.escape(word) for word in rule.threshold_source.split()),source)
            if not match:raise ExtractionValidationError('Threshold source must match clause')
            rule.threshold_source=match.group(0)
        numeric_values=[]
        for v in (rule.threshold_value,rule.lower_bound,rule.upper_bound):
            if isinstance(v,(float,int)) and not isinstance(v,bool):numeric_values.append(v)
            elif isinstance(v,list):numeric_values.extend(n for n in v if isinstance(n,(float,int)))
        if numeric_values:
            if not rule.threshold_source or rule.threshold_source not in source:raise ExtractionValidationError('Numeric threshold lacks exact source')
            tokens={float(t.replace(',','')) for t in re.findall(r'(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?',rule.threshold_source)}
            if any(float(value) not in tokens for value in numeric_values):raise ExtractionValidationError('Numeric threshold is not explicitly stated')
        # Operational classifications and authorities require source support;
        # plausible model guesses are kept null for the business reviewer.
        normalized_source=' '.join(source.lower().split())
        for property_name in ('data_source','approval_or_escalation_requirement','breach_consequence'):
            value=getattr(rule,property_name)
            if value and ' '.join(value.lower().split()) not in normalized_source:
                setattr(rule,property_name,None)
        if rule.severity and rule.severity.lower() not in normalized_source:
            rule.severity=None
        nullable=('metric_name' ,'metric_definition','operator','threshold_value','threshold_unit','lower_bound','upper_bound','threshold_source','calculation_logic','data_source','applicable_stage','severity','breach_consequence','exception_allowed','approval_or_escalation_requirement')
        rule.missing_information=sorted(set(rule.missing_information+[key for key in nullable if getattr(rule,key) is None]))
    return output


def extract_batch(clauses,version_id,job_id=None,client_factory=Mistral,return_contract=False,knowledge_context=None):
    if not MISTRAL_API_KEY:raise HTTPException(503,'MISTRAL_API_KEY is not configured')
    with shared_policy_connection() as c:
        source=c.execute("SELECT pv.policy_id,pv.version,doc.id AS document_id FROM policy_versions pv JOIN inventory_documents doc ON doc.policy_version_id=pv.id WHERE pv.id=%s",(version_id,)).fetchone()
    if not source:raise ValueError('Ingest the policy source before extraction')
    previous_error=None
    for attempt in range(1,RULE_EXTRACTION_RETRIES+1):
        execution_id=str(uuid4())
        with shared_policy_connection() as c:
            c.execute("INSERT INTO agent_execution_logs(id,job_id,policy_version_id,agent_name,model_name,prompt_version,status,attempt) VALUES (%s,%s,%s,'Credit Policy Rule Extraction Agent',%s,%s,'Running',%s)",(execution_id,job_id,version_id,MISTRAL_POLICY_MODEL,PROMPT_VERSION,attempt))
        try:
            report=CreditPolicyRuleExtractionAgent(client_factory=client_factory,api_key=MISTRAL_API_KEY).run(
                policy_id=source['policy_id'],policy_version=source['version'],source_document_id=source['document_id'],
                extraction_run_id=execution_id,clauses=clauses,previous_validation_error=previous_error,
                **({'knowledge_context':knowledge_context} if knowledge_context is not None else {}))
            output=to_inventory(report,clauses)
            validate_extraction(output,clauses)
            with shared_policy_connection() as c:
                c.execute('INSERT INTO policy_extraction_reports(id,policy_version_id,source_document_id,schema_version,output) VALUES (%s,%s,%s,%s,%s::jsonb)',(execution_id,version_id,source['document_id'],PROMPT_VERSION,report.model_dump_json()))
                c.execute("UPDATE agent_execution_logs SET status='Completed',finished_at=CURRENT_TIMESTAMP WHERE id=%s",(execution_id,))
            return report if return_contract else output
        except Exception as error:
            previous_error=(str(error) if isinstance(error,SourceValidationError) else [{'path':e['loc'],'type':e['type'],'constraint':e['msg'] if e['type']=='value_error' else e['type']} for e in error.errors(include_input=False,include_context=False)] if isinstance(error,ValidationError) else type(error).__name__)
            with shared_policy_connection() as c:
                c.execute("UPDATE agent_execution_logs SET status='Failed',error_code=%s,finished_at=CURRENT_TIMESTAMP WHERE id=%s",((str(error) if isinstance(error,SourceValidationError) else json.dumps([{'path':e['loc'],'type':e['type']} for e in error.errors(include_input=False,include_context=False)])[:2000] if isinstance(error,ValidationError) else type(error).__name__),execution_id))
            if attempt==RULE_EXTRACTION_RETRIES:raise ValueError('Rule extraction failed: '+(str(error) if isinstance(error,SourceValidationError) else type(error).__name__)) from error
            time.sleep(min(2,attempt))


def clause_batches(clauses):
    batch=[];size=0
    for clause in clauses:
        length=len(clause['source_excerpt'])
        if batch and (len(batch)>=RULE_CLAUSE_BATCH_SIZE or size+length>18000):
            yield batch;batch=[];size=0
        batch.append(clause);size+=length
    if batch:yield batch


def resolve_batch_failures(connection,batch_key,job_id,version_id,batch):
    connection.execute("""UPDATE inventory_batch_attempts SET retry_status='Resolved by retry'
        WHERE status='Failed' AND (batch_key=%s OR (job_id=%s::uuid AND policy_version_id=%s AND clause_ids=%s::jsonb))""",
        (batch_key,job_id,version_id,json.dumps([cl['id'] for cl in batch])))


def process_policy(policy_id,user,job_id=None,progress=None,knowledge=None):
    policy,version,document,clauses=knowledge.ingested if knowledge is not None else ingest_policy(policy_id)
    with shared_policy_connection() as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(f'extract:{version["id"]}',))
        current_extraction=c.execute('SELECT 1 FROM policy_extraction_reports WHERE policy_version_id=%s AND schema_version=%s AND EXISTS (SELECT 1 FROM policy_rule_versions WHERE policy_version_id=%s AND credit_data.is_quantitative_rule(definition)) LIMIT 1',(version['id'],PROMPT_VERSION,version['id'])).fetchone()
        if knowledge is None and job_id is None and document['extraction_status']=='Completed' and current_extraction:
            return {'policy_id':policy_id,'policy_name':policy['title'],'status':'Already processed','clauses_processed':len(clauses),'rules_proposed':0,'quantitative_rules':0,'qualitative_rules':0,'manual_review_rules':0,'missing_thresholds':0,'duplicate_candidates':0,'validation_failures':0}
        c.execute("UPDATE inventory_documents SET extraction_status='Running',error=NULL WHERE id=%s",(document['id'],))
    created=[];failed_batches=0;completed_clauses=0;batch_errors=[]
    batches=list(clause_batches(clauses))
    try:
        for index,batch in enumerate(batches,1):
            # Source-validated rules survive vocabulary changes within a retry.
            # Mapping against the current vocabulary is repeated by annotate().
            context_key=':'+knowledge.context_fingerprint if knowledge is not None else ''
            base_key=str(version['id'])+':'+','.join(str(c['id']) for c in batch)+':'+PROMPT_VERSION
            suffix=':'+str(job_id) if job_id else ''
            batch_key=hashlib.sha256((base_key+suffix).encode()).hexdigest()
            with shared_policy_connection() as c:
                checkpoint=c.execute('SELECT * FROM rule_extraction_batches WHERE batch_key=%s',(batch_key,)).fetchone()
                if checkpoint is None and knowledge is not None:
                    legacy_key=hashlib.sha256((base_key+context_key+suffix).encode()).hexdigest()
                    checkpoint=c.execute('SELECT * FROM rule_extraction_batches WHERE batch_key=%s',(legacy_key,)).fetchone()
                    if checkpoint:
                        c.execute('INSERT INTO rule_extraction_batches(policy_version_id,batch_key,rule_ids) VALUES (%s,%s,%s::jsonb) ON CONFLICT(batch_key) DO NOTHING',(version['id'],batch_key,json.dumps(checkpoint['rule_ids'])))
                # A retry of the same job may reuse source-validated groups from
                # the prior prompt. Their mappings are revalidated below.
                if checkpoint is None and knowledge is not None and job_id:
                    for previous_version in COMPATIBLE_CHECKPOINT_VERSIONS:
                        prior_key=hashlib.sha256((str(version['id'])+':'+','.join(str(cl['id']) for cl in batch)+':'+previous_version+context_key+':'+str(job_id)).encode()).hexdigest()
                        checkpoint=c.execute('SELECT * FROM rule_extraction_batches WHERE batch_key=%s',(prior_key,)).fetchone()
                        if checkpoint:
                            c.execute('INSERT INTO rule_extraction_batches(policy_version_id,batch_key,rule_ids) VALUES (%s,%s,%s::jsonb) ON CONFLICT(batch_key) DO NOTHING',(version['id'],batch_key,json.dumps(checkpoint['rule_ids'])))
                            break
            if checkpoint:
                with shared_policy_connection() as c:
                    checkpoint_rows=c.execute('SELECT * FROM policy_rule_versions WHERE id=ANY(%s)',(checkpoint['rule_ids'],)).fetchall()
                    created.extend(checkpoint_rows)
                if knowledge is not None:
                    knowledge.annotate(checkpoint_rows,batch)
                with shared_policy_connection() as c:
                    resolve_batch_failures(c,batch_key,job_id,version['id'],batch)
                completed_clauses+=len(batch)
                if progress:progress(index)
                continue
            try:
                output=extract_batch(batch,version['id'],job_id,**({'knowledge_context':knowledge.batch_context(batch)} if knowledge is not None else {}))
            except ValueError as error:
                failed_batches+=1
                batch_errors.append({'batch_number':index,'clause_ids':[cl['id'] for cl in batch],'message':str(error)[:2000]})
                with shared_policy_connection() as c:
                    attempt=c.execute('SELECT COUNT(*)+1 AS n FROM inventory_batch_attempts WHERE batch_key=%s',(batch_key,)).fetchone()['n']
                    c.execute("INSERT INTO inventory_batch_attempts(job_id,policy_version_id,batch_key,clause_ids,status,attempt,error_code,error_details,retry_status) VALUES (%s,%s,%s,%s::jsonb,'Failed',%s,%s,%s,'Retry available')",(job_id,version['id'],batch_key,json.dumps([cl['id'] for cl in batch]),attempt,type(error).__name__,str(error)[:2000]))
                if progress:progress(index)
                continue
            with shared_policy_connection() as c:
                c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(batch_key,))
                checkpoint=c.execute('SELECT * FROM rule_extraction_batches WHERE batch_key=%s',(batch_key,)).fetchone()
                if checkpoint:continue
                rows=[]
                for proposed in output.rules:
                    key=hashlib.sha256(f'{version["id"]}:{proposed.clause_id}:{proposed.rule_sequence}:{PROMPT_VERSION}:{job_id or "default"}'.encode()).hexdigest()
                    if knowledge is not None:
                        key='risk-knowledge:'+key
                    definition=GovernedDefinition(**proposed.model_dump(),change_rationale='AI extraction from policy source; automatic approval workflow')
                    rows.append(store_rule(GovernedRuleInput(policy_id=policy_id,definition=definition,effective_from=version['effective_date'] or date.today()),user,extraction_key=key,c=c,**({'force_draft':True} if knowledge is not None else {})))
                c.execute('INSERT INTO rule_extraction_batches(policy_version_id,batch_key,rule_ids) VALUES (%s,%s,%s::jsonb)',(version['id'],batch_key,json.dumps([r['id'] for r in rows])))
                created.extend(rows)
            if knowledge is not None:
                knowledge.annotate(rows,batch)
            completed_clauses+=len(batch)
            with shared_policy_connection() as c:
                resolve_batch_failures(c,batch_key,job_id,version['id'],batch)
            if progress:progress(index)
        with shared_policy_connection() as c:
            all_rows=c.execute('SELECT DISTINCT ON (rule_key) * FROM policy_rule_versions WHERE credit_data.is_quantitative_rule(definition) AND policy_version_id=%s ORDER BY rule_key,version DESC,id DESC',(version['id'],)).fetchall()
            if not created:
                raise ValueError('No supported quantitative rules found. At least one source-backed quantitative rule is required per policy document; check the document for numeric requirements.')
            for row in all_rows:
                for other in all_rows:
                    if other['id']<=row['id']:continue
                    left=row['definition'];right=other['definition']
                    similar=SequenceMatcher(None,left['rule_description'].lower(),right['rule_description'].lower()).ratio()>=0.85
                    if similar:
                        c.execute("INSERT INTO rule_relationships(rule_version_id,related_rule_version_id,relationship_type,reason) VALUES (%s,%s,'Duplicate candidate','Similar descriptions; human review required') ON CONFLICT DO NOTHING",(row['id'],other['id']))
                c.execute("DELETE FROM rule_relationships WHERE rule_version_id=%s AND relationship_type IN ('AND','OR')",(row['id'],))
                for dependency in row['definition'].get('dependencies',[]):
                    targets=[r for r in all_rows if r['clause_id']==dependency['clause_id'] and r['definition']['rule_sequence']==dependency['rule_sequence'] and r['id']!=row['id']]
                    target=max(targets,key=lambda r:r['version']) if targets else None
                    if target and target['id']!=row['id']:
                        c.execute('INSERT INTO rule_relationships(rule_version_id,related_rule_version_id,relationship_type,reason) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',(row['id'],target['id'],dependency['relationship'],'Extracted compound requirement; reviewer must confirm'))
                    elif not target:
                        raise ValueError('Unresolved rule dependency; review extraction output')
            failures=c.execute("SELECT COUNT(*) AS n FROM agent_execution_logs WHERE policy_version_id=%s AND status='Failed' AND (%s::uuid IS NULL OR job_id=%s::uuid)",(version['id'],job_id,job_id)).fetchone()['n']
            duplicates=c.execute("SELECT COUNT(*) AS count FROM rule_relationships rel JOIN policy_rule_versions r ON r.id=rel.rule_version_id WHERE r.policy_version_id=%s AND rel.relationship_type='Duplicate candidate'",(version['id'],)).fetchone()['count']
            c.execute("UPDATE inventory_documents SET extraction_status=%s,processed_at=CURRENT_TIMESTAMP,error=%s WHERE id=%s",('Failed' if failed_batches else 'Completed',f'{failed_batches} clause groups failed; retry available' if failed_batches else None,document['id']))
        definitions=[r['definition'] for r in created]
        result={'policy_id':policy_id,'policy_name':policy['title'],'status':'Failed' if failed_batches else 'Completed','clauses_discovered':len(clauses),'clauses_processed':completed_clauses,'failed_batches':failed_batches,'total_batches':len(batches),'batch_errors':batch_errors,'rules_proposed':len(created),'quantitative_rules':sum(d['rule_type']=='quantitative' for d in definitions),'qualitative_rules':sum(d['rule_type']!='quantitative' for d in definitions),'manual_review_rules':sum(d.get('calculation_logic') is None or d['calculation_logic']['method']=='manual' or bool(d.get('missing_information')) for d in definitions),'missing_thresholds':sum(d.get('threshold_value') is None for d in definitions),'duplicate_candidates':duplicates,'validation_failures':failures}
        result['validation_attempt_failures']=failures
        result['validation_failures']=failed_batches
        if failed_batches:
            result['error']=f"{failed_batches} of {len(batches)} clause groups failed; {len(created)} draft rules were saved. "+batch_errors[0]['message']
        return result
    except Exception as error:
        with shared_policy_connection() as c:
            partial=c.execute('SELECT definition FROM policy_rule_versions WHERE id=ANY(%s)',([row['id'] for row in created],)).fetchall()
            c.execute("UPDATE inventory_documents SET extraction_status='Failed',error=%s WHERE id=%s",(str(error)[:2000] if isinstance(error,ValueError) else type(error).__name__,document['id']))
            failures=c.execute("SELECT COUNT(*) AS n FROM agent_execution_logs WHERE policy_version_id=%s AND status='Failed' AND (%s::uuid IS NULL OR job_id=%s::uuid)",(version['id'],job_id,job_id)).fetchone()['n']
        definitions=[r['definition'] for r in partial]
        return {'policy_id':policy_id,'policy_name':policy['title'],'status':'Failed','error':str(error) if isinstance(error,ValueError) else type(error).__name__,'clauses_processed':completed_clauses,'clauses_discovered':len(clauses),'rules_proposed':len(partial),'quantitative_rules':sum(d['rule_type']=='quantitative' for d in definitions),'qualitative_rules':sum(d['rule_type']!='quantitative' for d in definitions),'manual_review_rules':sum(bool(d.get('missing_information')) for d in definitions),'missing_thresholds':sum(d.get('threshold_value') is None for d in definitions),'validation_failures':max(1,failed_batches),'validation_attempt_failures':failures,'duplicate_candidates':0}


@account_ai_job
def run_inventory_job(job_id,user):
    from threading import Event,Thread
    with shared_policy_connection() as c:
        job=c.execute("UPDATE rule_inventory_jobs SET status='Running',started_at=CURRENT_TIMESTAMP,heartbeat_at=CURRENT_TIMESTAMP WHERE id=%s AND status='Queued' RETURNING *",(job_id,)).fetchone()
    if not job:return
    stopped=Event()
    def keep_alive():
        while not stopped.wait(30):
            try:
                with shared_policy_connection() as c:
                    c.execute("UPDATE rule_inventory_jobs SET heartbeat_at=CURRENT_TIMESTAMP WHERE id=%s AND status='Running'",(job_id,))
            except Exception:
                logger.exception('Could not update extraction heartbeat for %s',job_id)
    heartbeat=Thread(target=keep_alive,name='inventory-heartbeat',daemon=True)
    heartbeat.start()
    try:
        _process_inventory_job(job_id,user,job)
    except Exception as error:
        logger.exception('Extraction job %s failed',job_id)
        reason=str(error)[:2000] if isinstance(error,ValueError) else type(error).__name__
        with shared_policy_connection() as c:
            c.execute("""UPDATE rule_inventory_jobs SET status=CASE WHEN COALESCE((report->>'rules_proposed')::integer,0)>0
                THEN 'Completed with errors' ELSE 'Failed' END,error=%s,finished_at=CURRENT_TIMESTAMP,
                heartbeat_at=CURRENT_TIMESTAMP WHERE id=%s""",(reason,job_id))
    finally:
        stopped.set()
        heartbeat.join(timeout=2)


def _process_inventory_job(job_id,user,job):
    from concurrent.futures import ThreadPoolExecutor,as_completed
    from threading import Lock
    from .inventory_operations import run_quality_reviews
    from ..risk_knowledge.pipeline import process_policy as process_risk_policy, PIPELINE_VERSION
    lock=Lock();report={}
    # Retry the unfinished documents; retain successful results from this job.
    progress={p['policy_id']:p for p in job.get('progress',[]) if p['policy_id'] in job['policy_ids']
              and p['status'] in ('Completed','Already processed') and not p.get('partial_result')
              and not p.get('failed_batches') and not p.get('error')}
    counts=('clauses_processed','rules_proposed','quantitative_rules','qualitative_rules','manual_review_rules','missing_thresholds','validation_failures','duplicate_candidates',
            'clauses_classified','taxonomy_proposals','ontology_proposals','rules_mapped','unresolved_mappings','rules_approved')
    def persist_progress():
        nonlocal report
        ordered=[progress[pid] for pid in job['policy_ids'] if pid in progress]
        report={key:sum(p.get(key,0) for p in ordered) for key in counts}
        report['pipeline']=PIPELINE_VERSION
        report['policies_processed']=sum(p['status'] in ('Completed','Already processed') for p in ordered)
        report['policies_failed']=sum(p['status'] in ('Failed','Completed with errors') for p in ordered)
        with shared_policy_connection() as c:
            c.execute('UPDATE rule_inventory_jobs SET progress=%s::jsonb,report=%s::jsonb,heartbeat_at=CURRENT_TIMESTAMP WHERE id=%s',(json.dumps(ordered),json.dumps(report),job_id))
    def process(policy_id):
        def heartbeat(batch_no,stage=None,details=None):
            with lock:
                progress[policy_id]={**progress.get(policy_id,{}),'policy_id':policy_id,'status':'Running','completed_batches':batch_no,
                                     **({'stage':stage} if stage else {}),**(details or {})}
                persist_progress()
        heartbeat(0)
        try:return process_risk_policy(policy_id,user,job_id,heartbeat)
        except Exception as error:return {**progress.get(policy_id,{}),'policy_id':policy_id,'status':'Failed','error':str(error) if isinstance(error,ValueError) else type(error).__name__,'validation_failures':1}
    with ThreadPoolExecutor(max_workers=RULE_INVENTORY_WORKERS,thread_name_prefix='rule-inventory') as executor:
        futures={executor.submit(copy_context().run,process,pid):pid for pid in job['policy_ids'] if pid not in progress}
        for future in as_completed(futures):
            with lock:
                progress[futures[future]]=future.result()
                persist_progress()
    persist_progress()
    quality=run_quality_reviews(job_id,user)
    report.update(quality)
    with shared_policy_connection() as c:
        counts=c.execute("SELECT COUNT(*) AS rules_in_inventory,COUNT(*) FILTER (WHERE status='Draft') AS draft_rules,COUNT(*) FILTER (WHERE status='Active') AS active_rules FROM policy_rule_versions WHERE credit_data.is_quantitative_rule(definition) AND policy_id=ANY(%s)",(job['policy_ids'],)).fetchone()
        report.update(counts)
        status='Failed' if not report['rules_proposed'] else 'Completed with errors' if (
            report['policies_failed'] or report.get('quality_failed') or report.get('quality_pending')) else 'Completed'
        c.execute('UPDATE rule_inventory_jobs SET status=%s,report=%s::jsonb,error=NULL,finished_at=CURRENT_TIMESTAMP WHERE id=%s',(status,json.dumps(report),job_id))
