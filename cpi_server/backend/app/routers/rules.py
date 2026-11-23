import json
import math
from datetime import date
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from ..database import shared_policy_connection
from ..access_control import has_permission
from ..security import audit_export, current_user
from ..config import MISTRAL_API_KEY

router = APIRouter()

@router.get('/api/policy-agents')
def policy_agents(user=Depends(current_user)):
    from ..agents.credit_policy_rule_quality_review import CreditPolicyRuleQualityReviewAgent
    from ..agents.credit_request_policy_applicability import CreditRequestPolicyApplicabilityAgent
    from ..agents.credit_policy_compliance_explanation import CreditPolicyComplianceExplanationAgent
    return [{'name':agent.name,'version':agent.prompt_version,
             'implementation':'Mistral source review' if agent is CreditPolicyRuleQualityReviewAgent else 'Deterministic grounded agent',
             'output_schema':agent.output_model.model_json_schema()} for agent in
            (CreditPolicyRuleQualityReviewAgent,CreditRequestPolicyApplicabilityAgent,CreditPolicyComplianceExplanationAgent)]


@router.post('/api/policy-rules/{rule_id}/quality-review')
def quality_review(rule_id: int,user=Depends(current_user)):
    reviewer(user)
    from ..config import MISTRAL_POLICY_MODEL
    from ..agents.credit_policy_rule_quality_review import CreditPolicyRuleQualityReviewAgent
    with shared_policy_connection() as c:
        rule=c.execute('SELECT r.*,p.title,e.rule_code FROM policy_rule_versions r JOIN policy_documents p USING(policy_id) JOIN policy_rule_entities e ON e.id=r.rule_entity_id WHERE r.id=%s',(rule_id,)).fetchone()
        if not rule:raise HTTPException(404,'Rule version not found')
        clause=c.execute('SELECT * FROM policy_clauses WHERE id=%s',(rule['clause_id'],)).fetchone()
        if not clause:raise HTTPException(422,'An exact source clause is required for quality review')
        comparisons=c.execute('SELECT r.id,e.rule_code,r.definition FROM policy_rule_versions r JOIN policy_rule_entities e ON e.id=r.rule_entity_id WHERE r.policy_id=%s AND r.id<>%s ORDER BY (r.clause_id=%s) DESC,r.version DESC LIMIT 20',(rule['policy_id'],rule_id,rule['clause_id'])).fetchall()
    while comparisons and len(json.dumps({'proposed_rule':rule,'source_clause':clause,'comparison_rules':comparisons},default=str))>48000:
        comparisons.pop()
    if len(json.dumps({'proposed_rule':rule,'source_clause':clause,'comparison_rules':[]},default=str))>48000:
        raise HTTPException(422,'This source clause exceeds the agent review limit; use business review for this version')
    execution_id=str(uuid4())
    with shared_policy_connection() as c:
        c.execute("INSERT INTO agent_execution_logs(id,agent_name,model_name,prompt_version,status,attempt) VALUES (%s,%s,%s,%s,'Running',1)",(execution_id,CreditPolicyRuleQualityReviewAgent.name,MISTRAL_POLICY_MODEL,CreditPolicyRuleQualityReviewAgent.prompt_version))
    try:
        report=CreditPolicyRuleQualityReviewAgent().run(rule,clause,comparisons)
    except Exception:
        with shared_policy_connection() as c:
            c.execute("UPDATE agent_execution_logs SET status='Failed',error_code='QUALITY_REVIEW_FAILED',finished_at=CURRENT_TIMESTAMP WHERE id=%s",(execution_id,))
        raise HTTPException(502,'Quality review could not be completed; retry after checking agent configuration') from None
    # Advisory findings are never submitted to the approval or activation service.
    output={'rule_version_id':rule_id,'rule_version':rule['version'],'execution_id':execution_id,'advisory_only':True,'report':report}
    with shared_policy_connection() as c:
        c.execute("UPDATE agent_execution_logs SET status='Completed',finished_at=CURRENT_TIMESTAMP WHERE id=%s",(execution_id,))
        c.execute("INSERT INTO audit_events(entity_type,entity_id,previous_value,new_value,action,actor,reason) VALUES ('PolicyRuleVersion',%s,%s::jsonb,%s::jsonb,'AdvisoryQualityReview',%s,'AI quality findings for human review; governance status unchanged')",(str(rule_id),json.dumps({'definition':rule['definition'],'status':rule['status'],'active':rule['active']},default=str),json.dumps(output),str(user['user_id'])))
        from ..services.inventory_operations import definition_checksum
        c.execute("""INSERT INTO rule_quality_reports(rule_version_id,definition_checksum,prompt_version,execution_id,status,report,retry_status)
            VALUES (%s,%s,%s,%s,'Completed',%s::jsonb,'No retry needed')
            ON CONFLICT(rule_version_id,definition_checksum,prompt_version) DO UPDATE SET execution_id=EXCLUDED.execution_id,status='Completed',report=EXCLUDED.report,error_code=NULL,retry_status='No retry needed',created_at=CURRENT_TIMESTAMP""",
            (rule_id,definition_checksum(rule['definition']),CreditPolicyRuleQualityReviewAgent.prompt_version,execution_id,json.dumps(report)))
    return output
METRICS = {"requested_amount", "exposure", "rating", "industry", "facility", "geography_risk", "concentration_limit_utilization", "adjusted_collateral", "post_approval_exposure", "approval_authority", "total_required_documents", "uploaded_required_documents"}

# Legacy import-compatible types; operational routes use GovernedRuleInput.
class RuleDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    check: str = Field(min_length=1, max_length=2000)
    metric: str
    operator: Literal["<=", ">=", "==", "!=", "<", ">"]
    threshold: float | str
    stage_applicable: str = Field(min_length=1, max_length=100)
    severity: Literal["WARNING", "BREACH"] = "BREACH"
    data_source: str = Field(min_length=1, max_length=1000)
    calculation_logic: Literal["direct"] = "direct"
    evidence_requirements: str = Field(min_length=1, max_length=2000)
    source_evidence: str = Field(min_length=1, max_length=4000)
    applicability: dict[str, str] = Field(default_factory=dict)
    change_rationale: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_fields(self):
        if isinstance(self.threshold, float) and not math.isfinite(self.threshold):
            raise ValueError("Threshold must be finite")
        if self.metric not in METRICS or any(k not in METRICS for k in self.applicability):
            raise ValueError("Unsupported request attribute")
        if self.operator in ("<", ">", "<=", ">=") and not isinstance(self.threshold, (int, float)):
            raise ValueError("Numeric comparisons require a numeric threshold")
        return self

class RuleInput(BaseModel):
    policy_id: int
    definition: RuleDefinition
    effective_from: date
    effective_to: date | None = None
    @model_validator(mode="after")
    def dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Effective-to must follow effective-from")
        return self

class Action(BaseModel):
    action: Literal["submit", "approve", "reject", "retire", "activate", "deactivate", "comment"]
    comment: str = Field(min_length=1, max_length=2000)
    @model_validator(mode="after")
    def meaningful_comment(self):
        self.comment=self.comment.strip()
        if not self.comment:raise ValueError("A review reason is required")
        return self


def reviewer(user):
    if not has_permission(user, "policy.review"):
        raise HTTPException(403, "A credit analyst or administrator must review rules")

from fastapi import BackgroundTasks
from fastapi.responses import FileResponse
from pathlib import Path
from ..database import db_connection
from ..config import BASE_DIR, RULE_DEMO_AUTO_APPROVE
from ..services.inventory_schema import GovernedRuleInput
from ..services.rule_governance import store_rule, change_status
from ..services.rule_extraction import run_background_inventory_job

@router.get("/api/policy-rules")
def inventory(policy_id: int | None = None, origin: Literal['graph','history','all']='graph', user=Depends(current_user)):
    from ..services.policy_ingestion import reconcile_policy_sources
    reconcile_policy_sources()
    with shared_policy_connection() as c:
        rows=c.execute("""SELECT r.*,p.title AS policy_name,p.file_name,e.rule_code,e.id AS rule_id,r.id AS rule_version_id,r.approval_date AS approved_at,
            cl.section_heading AS source_section,cl.clause_number AS source_clause,
            cl.page_number AS source_page,doc.id AS source_document_id,p.source_type,q.status AS quality_status,q.report AS quality_report,q.error_code AS quality_error,q.definition_checksum AS quality_checksum,
            (r.policy_version_id IS NULL OR NOT COALESCE(pv.is_current,false)
             OR p.version<>r.policy_version OR md5(p.summary)<>r.policy_fingerprint) AS review_required,
                   rk.payload AS risk_knowledge,pv.checksum AS source_checksum,
                   representation.payload->>'content_digest' AS current_representation_digest,
                   representation.payload AS source_representation,
                   dependency_review.payload AS dependency_review,
                   EXISTS(SELECT 1 FROM rule_relationships rel WHERE
                (rel.rule_version_id=r.id OR rel.related_rule_version_id=r.id)
                AND rel.relationship_type='Duplicate candidate') AS duplicate_candidate
            FROM policy_rule_versions r JOIN policy_documents p USING(policy_id)
            LEFT JOIN policy_rule_entities e ON e.id=r.rule_entity_id
            LEFT JOIN policy_versions pv ON pv.id=r.policy_version_id
            LEFT JOIN policy_clauses cl ON cl.id=r.clause_id
            LEFT JOIN inventory_documents doc ON doc.id=cl.document_id
            LEFT JOIN risk_knowledge_objects rk ON rk.kind='metadata' AND rk.owner_id='' AND rk.id='CPI-RULE-'||r.id::text
            LEFT JOIN risk_knowledge_objects representation ON representation.kind='metadata' AND representation.owner_id='' AND representation.id=r.definition->>'representation_id'
            LEFT JOIN risk_knowledge_objects dependency_review ON dependency_review.kind='metadata' AND dependency_review.owner_id='' AND dependency_review.id='RULE-DEPENDENCIES-'||r.rule_key
            LEFT JOIN LATERAL (SELECT * FROM rule_quality_reports qr WHERE qr.rule_version_id=r.id ORDER BY qr.created_at DESC LIMIT 1) q ON true
            WHERE credit_data.is_supported_policy_rule(r.definition)
                AND (%s::bigint IS NULL OR r.policy_id=%s)
                AND NOT EXISTS (SELECT 1 FROM policy_rule_versions newer
                    WHERE newer.rule_key=r.rule_key AND newer.version>r.version)
            ORDER BY r.policy_id,e.rule_code,r.version DESC""",(policy_id,policy_id)).fetchall()

    from ..services.inventory_operations import definition_checksum
    from ..risk_knowledge.representation_governance import check_definition
    from ..risk_knowledge.policy_representation import compile_graph,representation_id
    compiled_cache={}
    for row in rows:
        row["quality_stale"]=bool(row.get("quality_checksum") and row["quality_checksum"]!=definition_checksum(row["definition"]))
        definition=row['definition']
        rep=row.pop('source_representation',None)
        row['origin']='graph' if definition.get('representation_id') else 'history'
        row['origin_label']='Graph-compiled rule' if row['origin']=='graph' else 'Historical extraction — not operational'
        if definition.get('representation_id')!=representation_id(row.get('policy_version_id'),row.get('source_checksum')):
            row['review_required']=True
        if row['origin']=='graph' and rep:
            try:
                if rep['id'] not in compiled_cache:compiled_cache[rep['id']]=compile_graph(rep,rep['source_clauses'])
                check_definition(row,rep,rep['source_clauses'],compiled=compiled_cache[rep['id']])
            except (HTTPException,ValueError):row['review_required']=True
        elif row['origin']=='graph':row['review_required']=True
        if row['origin']=='graph' and row['review_required']:
            row['origin']='history';row['origin_label']='Superseded graph representation — not operational'
        from ..risk_knowledge.rule_readiness import dependency_state
        review=row.pop('dependency_review',None)
        blockers=[]
        if row['origin']=='graph' and rep:
            dependency=dependency_state(row,rep,review)
            if not dependency['ready']:blockers.append(str(len(dependency['blockers']))+' relevant source sections need review')
            if not definition.get('data_source'):blockers.append('Assign input data source')
            if not definition.get('severity'):blockers.append('Assign operational severity')
        row['approval_blockers']=blockers
        row['operational_eligible']=row['origin']=='graph' and row['status'] in ('Approved','Active') and not blockers
        row['operational_status']=('Historical — not operational' if row['origin']=='history' else
            'Review required: '+ '; '.join(blockers) if blockers else
            'Eligible for applicability checks' if row['operational_eligible'] else 'Awaiting rule approval')
    return rows if origin=='all' else [row for row in rows if row['origin']==origin]


@router.get('/api/policy-rules/{rule_id}/readiness')
def rule_readiness(rule_id: int,user=Depends(current_user)):
    from ..risk_knowledge.rule_readiness import get_readiness
    from ..services.policy_ingestion import reconcile_policy_sources
    reconcile_policy_sources()
    with shared_policy_connection() as connection:
        row,rep,result=get_readiness(rule_id,connection)
    return result


from ..risk_knowledge.rule_readiness import RuleApproval


@router.post('/api/policy-rules/{rule_id}/approve-reviewed')
def approve_reviewed_rule(rule_id: int,body: RuleApproval,user=Depends(current_user)):
    from ..risk_knowledge.rule_readiness import approve_rule
    from ..services.policy_ingestion import reconcile_policy_sources
    reconcile_policy_sources()
    return approve_rule(rule_id,body,user)

@router.get("/api/policy-rules/{rule_id}/audit")
def history(rule_id: int,user=Depends(current_user)):
    with shared_policy_connection() as c:
        return c.execute("SELECT * FROM audit_events WHERE entity_type='PolicyRuleVersion' AND entity_id=%s ORDER BY id",(str(rule_id),)).fetchall()

@router.get("/api/policy-rules/{rule_id}/details")
def details(rule_id: int,user=Depends(current_user)):
    with shared_policy_connection() as c:
        rule=c.execute('SELECT * FROM policy_rule_versions WHERE id=%s',(rule_id,)).fetchone()
        if not rule:raise HTTPException(404,'Rule not found')
        result={'rule':rule,'versions':c.execute('SELECT id,version,status,active,effective_from,effective_to,approved_by,approval_date,superseded_version_id FROM policy_rule_versions WHERE rule_key=%s ORDER BY version DESC',(rule['rule_key'],)).fetchall(),
                'reviews':c.execute('SELECT * FROM rule_reviews WHERE rule_version_id=%s ORDER BY id',(rule_id,)).fetchall(),
                'relationships':c.execute('SELECT * FROM rule_relationships WHERE rule_version_id=%s OR related_rule_version_id=%s',(rule_id,rule_id)).fetchall()}
        knowledge=c.execute("SELECT payload FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=%s",('CPI-RULE-'+str(rule_id),)).fetchone()
        result['risk_knowledge']=knowledge['payload'] if knowledge else None
    with db_connection() as c:
        result['assessments']=c.execute('SELECT a.id,a.request_id,a.result,a.evaluated_at,run.review_id FROM request_rule_assessments a JOIN rule_assessment_runs run ON run.id=a.run_id AND run.user_id=a.user_id WHERE a.rule_version_id=%s ORDER BY a.evaluated_at DESC LIMIT 100',(rule_id,)).fetchall()
    return result

@router.get("/api/policies/{policy_id}/clauses")
def clauses(policy_id: int,user=Depends(current_user)):
    with shared_policy_connection() as c:
        return c.execute('SELECT cl.*,pv.version,doc.file_name,doc.ingestion_status,doc.extraction_status FROM policy_clauses cl JOIN policy_versions pv ON pv.id=cl.policy_version_id JOIN inventory_documents doc ON doc.id=cl.document_id WHERE pv.policy_id=%s AND pv.is_current ORDER BY cl.sequence',(policy_id,)).fetchall()

@router.get("/api/inventory/documents/{document_id}/source")
def source_document(document_id: int, request: Request, user=Depends(current_user)):
    with shared_policy_connection() as c:
        doc=c.execute('SELECT COALESCE(doc.source_path,p.local_pdf_path) AS local_pdf_path,doc.file_name,doc.checksum FROM inventory_documents doc JOIN policy_documents p ON p.policy_id=doc.source_document_id WHERE doc.id=%s',(document_id,)).fetchone()
    if not doc:raise HTTPException(404,'Source document not found')
    path=Path(doc['local_pdf_path']).resolve()
    if not path.is_relative_to(BASE_DIR.resolve()) or not path.is_file():raise HTTPException(404,'Source file is unavailable')
    import hashlib
    if hashlib.sha256(path.read_bytes()).hexdigest()!=doc['checksum']:
        raise HTTPException(409,'The source file changed; the original version is unavailable')
    audit_export(request, user, f"inventory-document:{document_id}")
    return FileResponse(path,filename=doc['file_name'])

@router.post("/api/policy-rules")
def create(payload: GovernedRuleInput,user=Depends(current_user)):
    if not has_permission(user, "policy.create"):
        raise HTTPException(403, "Policy rule creation is unavailable")
    return store_rule(payload,user)

@router.put("/api/policy-rules/{rule_id}")
def revise(rule_id: int,payload: GovernedRuleInput,user=Depends(current_user)):
    if not has_permission(user, "policy.update"):
        raise HTTPException(403, "Policy rule editing is unavailable")
    row=store_rule(payload,user,previous=rule_id)
    if str(row.get('extraction_key') or '').startswith('risk-knowledge:'):
        from ..risk_knowledge.pipeline import refresh_rule_evidence
        from ..services.automatic_approval import approve_rules
        try:
            refresh_rule_evidence(row,user,shared_policy_connection)
        except ValueError:
            raise HTTPException(422, "Check the rule definition and its policy evidence before saving.") from None
        approve_rules(shared_policy_connection,[row['id']])
        with shared_policy_connection() as c:
            return c.execute('SELECT * FROM policy_rule_versions WHERE id=%s',(row['id'],)).fetchone()
    return row

@router.post("/api/policy-rules/{rule_id}/actions")
def action(rule_id: int,payload: Action,user=Depends(current_user)):
    return change_status(rule_id,payload.action,payload.comment,user)

class InventoryJobInput(BaseModel):
    policy_ids: list[int] | None = Field(default=None,max_length=1000)

def enqueue_inventory(user,policy_ids=None):
    if not MISTRAL_API_KEY:raise HTTPException(503,'MISTRAL_API_KEY is not configured')
    from ..services.inventory_operations import discover_documents
    documents=discover_documents(register=has_permission(user, "admin.manage"))
    with shared_policy_connection() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('rule-inventory-job'))")
        c.execute("UPDATE rule_inventory_jobs SET status='Failed',error='Worker interrupted; retry resumes completed batches',finished_at=CURRENT_TIMESTAMP WHERE status IN ('Queued','Running') AND COALESCE(heartbeat_at,created_at)<CURRENT_TIMESTAMP-INTERVAL '30 minutes'")
        c.execute("UPDATE agent_execution_logs SET status='Failed',error_code='Worker interrupted',finished_at=CURRENT_TIMESTAMP WHERE status='Running' AND job_id IN (SELECT id FROM rule_inventory_jobs WHERE status='Failed')")
        existing=c.execute("SELECT * FROM rule_inventory_jobs WHERE status IN ('Queued','Running')").fetchone()
        if existing:raise HTTPException(409,'An inventory generation job is already running')
        policies=c.execute("SELECT policy_id FROM policy_documents WHERE lower(status) IN ('active','pending metadata') AND (%s::bigint[] IS NULL OR policy_id=ANY(%s)) ORDER BY policy_id",(policy_ids,policy_ids)).fetchall()
        if not policies:raise HTTPException(409,'No active policy documents were selected')
        from ..risk_knowledge.pipeline import PIPELINE_VERSION
        return c.execute("INSERT INTO rule_inventory_jobs(id,status,policy_ids,created_by,discovered_documents,report) VALUES (%s,'Queued',%s::jsonb,%s,%s::jsonb,%s::jsonb) RETURNING *",(str(uuid4()),json.dumps([p['policy_id'] for p in policies]),user['user_id'],json.dumps(documents),json.dumps({'pipeline':PIPELINE_VERSION}))).fetchone()


@router.get('/api/inventory/documents')
def discovered_documents(user=Depends(current_user)):
    from ..services.inventory_operations import discover_documents
    return discover_documents()


@router.get('/api/inventory/jobs/{job_id}/exceptions')
def download_exceptions(job_id: str, request: Request, user=Depends(current_user)):
    from fastapi.responses import Response
    from ..services.inventory_operations import exception_report
    from uuid import UUID
    try:uuid4_value=UUID(job_id)
    except ValueError:raise HTTPException(422,'Invalid inventory job ID')
    try:report=exception_report(str(uuid4_value))
    except ValueError:raise HTTPException(404,'Inventory job not found')
    audit_export(request, user, f"inventory-exceptions:{uuid4_value}")
    return Response(json.dumps(report,default=str,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="inventory-exceptions-{uuid4_value}.json"'})


@router.post('/api/inventory/assess-synthetic-requests')
def reassess_synthetic_requests(user=Depends(current_user)):
    reviewer(user)
    from ..services.inventory_operations import assess_synthetic_requests
    return assess_synthetic_requests(user)


class SelectedDemoAction(BaseModel):
    rule_ids: list[int] = Field(min_length=1,max_length=50)
    action: Literal['submit','approve','activate']
    comment: str = Field(min_length=1,max_length=2000)


@router.post('/api/inventory/selected-demo-rules/actions')
def selected_demo_action(payload: SelectedDemoAction,user=Depends(current_user)):
    reviewer(user)
    if not payload.comment.strip():raise HTTPException(422,'A business review rationale is required')
    results=[]
    for rule_id in dict.fromkeys(payload.rule_ids):
        with shared_policy_connection() as c:
            row=c.execute('SELECT p.source_type FROM policy_rule_versions r JOIN policy_documents p USING(policy_id) WHERE r.id=%s',(rule_id,)).fetchone()
        if not row or row['source_type']!='manufactured':
            results.append({'rule_id':rule_id,'status':'Failed','error':'Select a manufactured demonstration rule'});continue
        try:
            rule=change_status(rule_id,payload.action,payload.comment,user)
            results.append({'rule_id':rule_id,'status':rule['status'],'version':rule['version']})
        except HTTPException as error:results.append({'rule_id':rule_id,'status':'Failed','error':error.detail})
    return {'results':results,'action':payload.action,'human_reviewer':user['user_id']}

@router.post("/api/inventory/generate")
def generate(payload: InventoryJobInput,background: BackgroundTasks,user=Depends(current_user)):
    if not has_permission(user, "policy.extraction.execute"):
        raise HTTPException(403,'Rule extraction is unavailable for this role')
    if not has_permission(user, "admin.manage") and not payload.policy_ids:
        raise HTTPException(422,'Select at least one policy document')
    job=enqueue_inventory(user,payload.policy_ids)
    background.add_task(run_background_inventory_job,str(job['id']),user)
    return job

@router.post("/api/policies/{policy_id}/propose-rules")
def propose(policy_id: int,background: BackgroundTasks,user=Depends(current_user)):
    reviewer(user)
    if not has_permission(user, "policy.extraction.execute"):
        raise HTTPException(403, "Rule extraction is unavailable for this role")
    job=enqueue_inventory(user,[policy_id])
    background.add_task(run_background_inventory_job,str(job['id']),user)
    return job

@router.get("/api/inventory/jobs")
def jobs(user=Depends(current_user)):
    from ..services.extraction_failures import attach_failures
    with shared_policy_connection() as c:
        c.execute("UPDATE rule_inventory_jobs SET status='Failed',error='Worker interrupted; retry resumes completed batches',finished_at=CURRENT_TIMESTAMP WHERE status IN ('Queued','Running') AND COALESCE(heartbeat_at,created_at)<CURRENT_TIMESTAMP-INTERVAL '30 minutes'")
        rows=c.execute('SELECT * FROM rule_inventory_jobs ORDER BY created_at DESC LIMIT 20').fetchall()
        return attach_failures(rows,c)

@router.get("/api/inventory/jobs/{job_id}")
def job_status(job_id: str,user=Depends(current_user)):
    from ..services.extraction_failures import attach_failures
    from uuid import UUID
    try:UUID(job_id)
    except ValueError:raise HTTPException(422,'Invalid inventory job ID')
    with shared_policy_connection() as c:
        job=c.execute('SELECT * FROM rule_inventory_jobs WHERE id=%s',(job_id,)).fetchone()
        if not job:raise HTTPException(404,'Inventory job not found')
        return attach_failures([job],c)[0]

@router.get("/api/inventory/config")
def inventory_config(user=Depends(current_user)):
    return {'demo_auto_approve_enabled':RULE_DEMO_AUTO_APPROVE and has_permission(user, "admin.manage")}

@router.post("/api/policy-rules/{rule_id}/demo-approve")
def demo_approve(rule_id: int,user=Depends(current_user)):
    if not has_permission(user, "admin.manage") or not RULE_DEMO_AUTO_APPROVE:raise HTTPException(403,'Demo approval is disabled')
    with shared_policy_connection() as c:
        rule=c.execute('SELECT r.status,p.source_type FROM policy_rule_versions r JOIN policy_documents p USING(policy_id) WHERE r.id=%s',(rule_id,)).fetchone()
    if not rule or rule['source_type']!='manufactured':raise HTTPException(403,'Only selected manufactured synthetic rules may use demo approval')
    if rule['status']=='Draft':change_status(rule_id,'submit','Development-only synthetic demo review',user)
    return change_status(rule_id,'approve','Development-only synthetic demo approval; activation remains separate',user)


@router.get("/api/policy-rule-agent")
def extraction_agent_contract(user=Depends(current_user)):
    from ..agents.credit_policy_rule_extraction import AGENT_NAME,PROMPT_VERSION
    from ..services.credit_policy_extraction_schema import CreditPolicyExtractionReport
    from ..config import MISTRAL_POLICY_MODEL
    return {'name':AGENT_NAME,'model':MISTRAL_POLICY_MODEL,'prompt_version':PROMPT_VERSION,'output_schema':CreditPolicyExtractionReport.model_json_schema(),'requires_human_review':True,'proposed_status':'DRAFT'}


@router.get("/api/policies/{policy_id}/extraction-reports")
def extraction_reports(policy_id: int,user=Depends(current_user)):
    with shared_policy_connection() as c:
        rows=c.execute('SELECT report.output FROM policy_extraction_reports report JOIN policy_versions pv ON pv.id=report.policy_version_id WHERE pv.policy_id=%s ORDER BY report.created_at DESC LIMIT 100',(policy_id,)).fetchall()
    return [r['output'] for r in rows]


class ExtractionPreviewInput(BaseModel):
    clause_ids: list[int] = Field(min_length=1,max_length=10)


@router.post("/api/policies/{policy_id}/rule-extraction-preview")
def preview_rule_extraction(policy_id: int,payload: ExtractionPreviewInput,user=Depends(current_user)):
    reviewer(user)
    from ..services.policy_ingestion import ingest_policy
    from ..services.rule_extraction import extract_batch
    with shared_policy_connection() as connection:
        if not connection.execute('SELECT policy_id FROM policy_documents WHERE policy_id=%s',(policy_id,)).fetchone():
            raise HTTPException(404,'Policy document not found')
    try:
        policy,version,document,clauses=ingest_policy(policy_id)
    except (ValueError,OSError):
        raise HTTPException(422,'The registered policy source could not be processed; check ingestion status') from None
    requested=set(payload.clause_ids)
    selected=[clause for clause in clauses if clause['id'] in requested]
    if len(selected)!=len(requested):raise HTTPException(422,'Select source spans belonging to this current policy version')
    if sum(len(clause['source_excerpt']) for clause in selected)>18000:
        raise HTTPException(422,'Choose fewer source spans for a bounded preview')
    try:
        return extract_batch(selected,version['id'],return_contract=True)
    except ValueError:
        raise HTTPException(502,'Agent output failed structured source validation; retry with a smaller source group') from None
