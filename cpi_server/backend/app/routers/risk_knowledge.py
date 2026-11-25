"""Authenticated extension of the existing CPI API, not a second application."""
from datetime import date
from pathlib import Path
from threading import RLock
from typing import Literal
from xml.etree.ElementTree import ParseError
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import Field
from fastapi.responses import FileResponse
from pypdf.errors import PdfReadError
from openpyxl.utils.exceptions import InvalidFileException
from ..config import BASE_DIR, RISK_SCHEMA_DIR, is_seed_policy_source, resolve_policy_source, resolve_seed_source, risk_schema_path
from ..database import shared_policy_connection
from ..access_control import has_permission
from ..security import audit_export, current_user
from ..risk_knowledge.catalog import read_catalog, documents_from_catalog, project_catalog
from ..risk_knowledge.competency_queries import Question
from ..risk_knowledge.ingestion import MAX_BYTES
from ..risk_knowledge.models import CreditRequest, Model, Review
from ..risk_knowledge.repositories import PostgreSQLRepository
from ..risk_knowledge.service import IntelligenceService
from ..services.policy_scope_governance import PolicyScopeInput, scope_context, approve_scope
from ..risk_knowledge.representation_governance import SourceInterpretationReview, current_representation,review_span
from ..risk_knowledge.policy_representation import coverage_summary,frame_from_graph,graph_from_representation

router = APIRouter(prefix='/api/risk-knowledge', tags=['Risk Knowledge'], dependencies=[Depends(current_user)])
lock = RLock()


@router.get('/policy-ontology')
def policy_ontology():
    return business_semantic_model()


@router.get('/semantic-model')
def business_semantic_model():
    from ..risk_knowledge.semantic_model import semantic_contract
    return semantic_contract()


def semantic_repository():
    return PostgreSQLRepository(shared_policy_connection, None)


@router.get('/semantic-knowledge')
def semantic_knowledge():
    from ..services.current_knowledge import inventory
    return inventory()


@router.get('/semantic-graph')
def semantic_graph(focus: str='', policy_id: int | None=None, offset: int=0, limit: int=6):
    from ..risk_knowledge.semantic_pipeline import current_records
    from ..risk_knowledge.semantic_view import graph_view
    return invoke(lambda: graph_view(current_records(semantic_repository()), focus=focus, policy_id=policy_id, offset=offset, limit=limit))


@router.post('/semantic-graph/rebuild')
def rebuild_reviewed_graph(user=Depends(current_user)):
    from ..services.policy_graph_rebuild import rebuild_summary, store_snapshot
    from ..services.semantic_matching import load_matcher
    if not has_permission(user, 'policy.extraction.execute'):
        raise HTTPException(403, 'Policy graph rebuild is unavailable for this role')
    with shared_policy_connection() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('rule-inventory-job'))")
        if connection.execute("SELECT 1 FROM rule_inventory_jobs WHERE status IN ('Queued','Running')").fetchone():
            raise HTTPException(409, 'Wait for the current policy extraction to finish')
        matcher = load_matcher()
        summary = invoke(lambda: rebuild_summary(matcher))
        store_snapshot(connection, matcher, summary)
    return summary


@router.get('/semantic-questions')
def semantic_questions(question: Question, value: str = Query(default='', max_length=240),
                       policy_id: int | None = Query(default=None, gt=0), on_date: date | None = None,
                       request_id: str = Query(default='', max_length=120),
                       offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=50),
                       user=Depends(current_user)):
    from ..risk_knowledge.competency_queries import answer
    from ..services.semantic_matching import load_matcher
    from ..services.rule_assessment import assessment_request_context
    value, request_id = value.strip(), request_id.strip()
    if question == 'effective':
        if on_date is None or policy_id is None:
            raise HTTPException(422, 'Select a policy and effective date')
        return effective_rule_edition(policy_id, on_date, value, offset, limit)
    if question in ('industry', 'geography', 'product', 'policy_class') and not value:
        raise HTTPException(422, 'Enter a scope value or rule ID')
    if question == 'relationship':
        from ..risk_knowledge.semantic_model import RELATIONSHIPS
        if value not in RELATIONSHIPS:
            raise HTTPException(422, 'Choose a relationship from the ontology')
    if question == 'borrower' and not request_id:
        raise HTTPException(422, 'Enter an authorized credit request ID to resolve borrower facts')
    proposal = assessment_request_context(request_id, user)[1] if request_id else None
    return answer(load_matcher(), question, value, request=proposal, policy_id=policy_id, limit=limit, offset=offset)


def effective_rule_edition(policy_id, on_date, rule_id, offset, limit):
    from ..risk_knowledge.competency_projection import explicit_rule_code
    from ..risk_knowledge.competency_queries import rule_answer, version_on
    from ..services.semantic_matching import GraphMatcher
    with shared_policy_connection() as connection:
        versions = connection.execute('''SELECT v.id,v.version,v.effective_date,v.checksum FROM policy_versions v
            JOIN inventory_documents d ON v.id=d.policy_version_id WHERE v.policy_id=%s AND d.ingestion_status='Completed'
            ORDER BY v.effective_date,v.id''', (policy_id,)).fetchall()
        selected, reason = version_on(versions, on_date)
        records = connection.execute("""SELECT k.payload FROM risk_knowledge_objects k
            JOIN policy_versions v ON v.id=(k.payload->>'policy_version_id')::bigint
            WHERE k.kind='metadata' AND k.owner_id='' AND k.payload->>'kind' IN ('semantic_policy','semantic_policy_history')
            AND v.policy_id=%s AND v.checksum=k.payload->>'source_checksum'""", (policy_id,)).fetchall() if selected else []
    result = {'question': 'effective', 'on_date': on_date, 'policy_id': policy_id, 'selected_version': selected,
              'versions': versions, 'results': [], 'total': 0, 'next_offset': None, 'reason': reason}
    if not selected:
        return result
    available = [r['payload'] for r in records]
    record = next((r for r in available if r['policy_version_id'] == selected['id']), None)
    if record is None:
        return {**result, 'reason': 'The source version is registered. Its semantic rule extraction is unavailable.'}
    record = {**record, 'effective_date': str(selected['effective_date'])}
    matcher = GraphMatcher([record], [], [])
    date_label = on_date.isoformat()
    ids = [n['id'] for n in matcher.nodes.values() if n['type'] == 'PolicyRule' and all(
        matcher.nodes[p]['properties']['start_date'] <= date_label <= matcher.nodes[p]['properties'].get('end_date', '9999-12-31')
        for p in matcher.targets(n['id'], 'HAS_EFFECTIVE_PERIOD'))]
    if rule_id and rule_id not in ids:
        reference = next((r['extracted']['source_quote'] for version in available for r in version['rules'] if r['id'] == rule_id), None)
        code = explicit_rule_code(reference) if reference else rule_id.upper()
        matching = [rid for rid in ids if matcher.nodes[rid]['properties'].get('source_rule_code') == code] if code else []
        if not matching and reference:
            matching = [rid for rid in ids if ' '.join(matcher.rows[rid][1]['extracted']['source_quote'].split()) == ' '.join(reference.split())]
        if len(matching) != 1:
            return {**result, 'reason': 'Rule identity across these versions needs review. Query the whole policy edition to see its archived rules.'}
        ids = matching
    elif rule_id:
        ids = [rule_id]
    return {**result, 'total': len(ids), 'next_offset': offset + limit if offset + limit < len(ids) else None,
            'results': [rule_answer(matcher, rid) for rid in ids[offset:offset + limit]]}


@router.get('/semantic-policies/{policy_id}/representation')
def semantic_policy_representation(policy_id: int):
    from ..risk_knowledge.policy_taxonomy import source_rows
    from ..risk_knowledge.semantic_pipeline import current_records
    from ..risk_knowledge.semantic_extraction import approved_rules
    from ..risk_knowledge.semantic_view import policy_source_view, graph_view
    documents, clauses = source_rows(shared_policy_connection)
    document = next((d for d in documents if d['policy_id'] == policy_id), None)
    if document is None:
        raise HTTPException(404, 'Policy not found')
    records = current_records(semantic_repository())
    record = next((r for r in records if r['policy_id'] == policy_id), None)
    result = policy_source_view(document, clauses, record, approved_rules(records))
    result['graph'] = graph_view(records, policy_id=policy_id) if result['has_extraction'] else {
        'nodes': [], 'edges': [], 'next_offset': None, 'total_nodes': 0, 'truncated': False}
    return result


@router.get('/semantic-knowledge/export')
def export_semantic_knowledge(request: Request, user=Depends(current_user)):
    report = semantic_graph_export()
    audit_export(request, user, "risk-knowledge:graph")
    return report


def semantic_graph_export():
    from ..risk_knowledge.semantic_pipeline import current_records
    from ..risk_knowledge.semantic_extraction import assemble_graph
    return assemble_graph(current_records(semantic_repository()))


class SemanticReview(Model):
    rule_id: str
    expected_digest: str
    status: Literal['APPROVED','REJECTED','PROPOSED']
    notes: str = Field(min_length=3,max_length=4000)
    replacement: dict | None = None


class SemanticScopeReview(Model):
    expected_digest: str
    scope: dict
    status: Literal['APPROVED','PROPOSED','REJECTED']
    notes: str=Field(min_length=3,max_length=2000)


@router.post('/semantic-policies/{policy_id}/scope')
def semantic_scope_review(policy_id:int,body:SemanticScopeReview,user=Depends(current_user)):
    if not has_permission(user, "knowledge.review"):raise HTTPException(403,'A credit analyst or administrator must review scope')
    from ..risk_knowledge.semantic_scope import review_scope
    return invoke(lambda:review_scope(semantic_repository(),policy_id,body.expected_digest,body.scope,body.status,user['user_id'],body.notes))


@router.post('/semantic-rules/review')
def semantic_rule_review(body: SemanticReview, user=Depends(current_user)):
    if not has_permission(user, "knowledge.review"):
        raise HTTPException(403,'A credit analyst or administrator must override extracted knowledge')
    from ..risk_knowledge.semantic_pipeline import review_rule
    return invoke(lambda: review_rule(semantic_repository(),body.rule_id,status=body.status,
        notes=body.notes,actor=user['user_id'],expected_digest=body.expected_digest,replacement=body.replacement))


@router.get('/semantic-model/schema')
def business_semantic_schema():
    from ..risk_knowledge.semantic_model import instance_schema
    return instance_schema()


@router.get('/semantic-model/ontology.ttl')
def business_semantic_owl(request: Request, user=Depends(current_user)):
    from fastapi.responses import Response
    from ..risk_knowledge.semantic_rdf import ontology_graph
    content = ontology_graph().serialize(format='turtle')
    audit_export(request, user, "risk-knowledge:owl-ontology")
    return Response(content, media_type='text/turtle')


@router.get('/semantic-model/shapes.ttl')
def business_semantic_shapes(request: Request, user=Depends(current_user)):
    from fastapi.responses import Response
    from ..risk_knowledge.semantic_rdf import shapes_graph
    content = shapes_graph().serialize(format='turtle')
    audit_export(request, user, "risk-knowledge:shacl-shapes")
    return Response(content, media_type='text/turtle')


@router.get('/semantic-model/example')
def business_semantic_example():
    from ..risk_knowledge.semantic_model import example_instance
    return example_instance()


@router.post('/semantic-model/validate')
def validate_business_semantic_instance(body: dict):
    from ..risk_knowledge.semantic_model import validate_instance
    return validate_instance(body)


@router.get('/policy-representations/{policy_id}')
def policy_representation(policy_id: int,focus: str=''):
    return semantic_policy_representation(policy_id)


@router.post('/policy-representations/{policy_id}/review')
def review_policy_interpretation(policy_id: int,body: SourceInterpretationReview,user=Depends(current_user)):
    raise HTTPException(410, 'Use the current Policy Rule Library, Policy Evidence and graph-based Compliance Review.')


@router.get('/policies/{policy_id}/scope')
def policy_scope_context(policy_id: int):
    return scope_context(policy_id)


@router.put('/policies/{policy_id}/scope')
def approve_policy_scope(policy_id: int, body: PolicyScopeInput, user=Depends(current_user)):
    return approve_scope(policy_id, body, user)


@router.get('/requests/{request_id}/graph')
def request_graph(request_id: str, focus: str = '', offset: int = 0, limit: int = 6, user=Depends(current_user)):
    from ..services.rule_assessment import assessment_request_context
    from ..services.semantic_matching import load_matcher
    from ..services.semantic_request_graph import request_overlay
    from ..risk_knowledge.semantic_view import graph_view
    request_id,data=assessment_request_context(request_id,user)
    matcher=load_matcher();report=matcher.match(data)
    graph=invoke(lambda:graph_view(matcher.records,focus=focus,offset=offset,limit=limit,
                                  instance=matcher.graph,overlay=request_overlay(request_id,data)))
    decisions={d['candidate_id']:d for d in report['decisions'] if d['candidate_type']=='Rule'}
    graph['nodes']=[{**n,'applicability':decisions.get(n['id'],{}).get('applicability')} for n in graph['nodes']]
    return {**graph,'report':report,'knowledge_fingerprint':matcher.fingerprint}



def invoke(operation):
    try:
        with lock:
            return operation()
    except KeyError:
        raise HTTPException(404, 'Risk knowledge object not found') from None
    except (PdfReadError, ParseError, InvalidFileException):
        raise HTTPException(422, "The document could not be read. Check the file format and upload it again.") from None
    except ValueError:
        raise HTTPException(422, "Check the submitted risk knowledge data and try again.") from None


def reviewer(user=Depends(current_user)):
    if not has_permission(user, "knowledge.review"):
        raise HTTPException(403, 'A credit analyst or administrator must review or change risk knowledge')
    return user


def get_service(user=Depends(current_user)):
    service = IntelligenceService(repository=PostgreSQLRepository(shared_policy_connection, user['user_id']))
    invoke(lambda: service.bootstrap(risk_schema_path()))
    return service


def catalog(service):
    if not hasattr(service, '_catalog'):
        service._catalog = read_catalog(shared_policy_connection)
    return service._catalog


def project_source_representations(service):
    from ..risk_knowledge.policy_representation import current_representations,project_representations
    records=[r for r in service.repo.all('metadata') if r.get('kind')=='policy_representation']
    if records:
        with shared_policy_connection() as connection:
            versions=connection.execute('SELECT id,checksum FROM policy_versions WHERE is_current').fetchall()
        project_representations(service.graph,current_representations(records,versions),catalog(service)[2])


class PolicyExtractionInput(Model):
    policy_ids: list[int] = Field(min_length=1,max_length=1000)


@router.post('/policy-uploads', status_code=201)
def upload_policy_source(file: UploadFile = File(), version: str = Form(min_length=1, max_length=24),
                         effective_date: date = Form(), policy_id: int | None = Form(default=None, gt=0),
                         code: str = Form(default='', max_length=80), title: str = Form(default='', max_length=200),
                         user=Depends(current_user)):
    from ..services.policy_uploads import stage_policy_upload
    if not has_permission(user, 'policy.update' if policy_id else 'policy.create'):
        raise HTTPException(403, 'Policy upload is unavailable for this role')
    return stage_policy_upload(file, owner=user['user_id'], policy_id=policy_id, code=code, title=title,
                               version=version, effective_date=effective_date)


@router.post('/policy-uploads/{upload_id}/rebuild', status_code=202)
def rebuild_after_upload(upload_id: str, background: BackgroundTasks, user=Depends(current_user)):
    from uuid import UUID
    from .rules import enqueue_inventory
    from ..services.rule_extraction import run_background_inventory_job
    if not has_permission(user, 'policy.extraction.execute'):
        raise HTTPException(403, 'Rule extraction is unavailable for this role')
    try:
        identifier = str(UUID(upload_id))
    except ValueError:
        raise HTTPException(422, 'Invalid staged upload') from None
    job = enqueue_inventory(user, staged_upload=identifier)
    if job['status'] == 'Queued':
        background.add_task(run_background_inventory_job, str(job['id']), user)
    return {'job_id': job['id'], 'policy_id': job['policy_ids'][0], 'status': job['status']}


@router.post('/extractions')
def extract_policies(body: PolicyExtractionInput, background: BackgroundTasks, user=Depends(current_user)):
    """The library action uses the same durable jobs and Risk Knowledge worker."""
    from .rules import generate, InventoryJobInput
    if any(identifier<=0 for identifier in body.policy_ids):
        raise HTTPException(422,'Select valid policy documents')
    return generate(InventoryJobInput(policy_ids=list(dict.fromkeys(body.policy_ids))),background,user)


@router.post('/extractions/{job_id}/retry')
def retry_extraction(job_id: str, background: BackgroundTasks, user=Depends(current_user)):
    from uuid import UUID
    from ..services.rule_extraction import run_background_inventory_job
    if not has_permission(user, "policy.extraction.execute"):
        raise HTTPException(403,'Rule extraction is unavailable for this role')
    try:
        UUID(job_id)
    except ValueError:
        raise HTTPException(422,'Invalid inventory job ID') from None
    with shared_policy_connection() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('rule-inventory-job'))")
        job=c.execute('SELECT * FROM rule_inventory_jobs WHERE id=%s FOR UPDATE',(job_id,)).fetchone()
        if not job:
            raise HTTPException(404,'Inventory job not found')
        report=job.get('report') or {}
        # Older workers labelled partial outcomes Completed. Preserve recovery.
        incomplete=job.get('error') or report.get('policies_failed') or report.get('quality_failed') or report.get('quality_pending') or any(
            p.get('partial_result') or p.get('failed_batches') or p.get('status') in ('Failed','Completed with errors')
            for p in job.get('progress',[]))
        retryable=job['status'] in ('Failed','Completed with errors') or (job['status']=='Completed' and incomplete)
        if not retryable or not report.get('pipeline'):
            raise HTTPException(409,'Only unsuccessful Risk Knowledge jobs can be retried')
        if not has_permission(user, "knowledge.review") and job["created_by"] != user["user_id"]:
            raise HTTPException(403,'You can retry your own extraction jobs')
        if c.execute("SELECT 1 FROM rule_inventory_jobs WHERE status IN ('Queued','Running')").fetchone():
            raise HTTPException(409,'An extraction is already running')
        job=c.execute("UPDATE rule_inventory_jobs SET status='Queued',error=NULL,finished_at=NULL,heartbeat_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *",(job_id,)).fetchone()
    background.add_task(run_background_inventory_job,job_id,user)
    return job


@router.get('/state')
def state(service=Depends(get_service)):
    from ..services.current_knowledge import inventory
    from ..services.semantic_matching import load_matcher
    from ..risk_knowledge.semantic_model import semantic_contract
    matcher=load_matcher();knowledge=inventory(matcher)
    with shared_policy_connection() as db:
        policies=db.execute('SELECT * FROM policy_documents ORDER BY display_order,policy_id').fetchall()
    sources=documents_from_catalog(policies,[{**c,'version':next(d['version'] for d in matcher.documents if d['policy_id']==c['policy_id'])} for c in matcher.clauses.values()])
    reference=[d for d in service.repo.all('documents') if d.get('document_type') in ('schema','reference') and not d.get('synthetic')]
    concepts=[c for c in service.repo.all('taxonomy_concepts') if c.get('source',{}).get('origin')=='SOURCE_SCHEMA']
    model=semantic_contract()
    return {'documents':[{k:v for k,v in d.items() if k!='raw_text'} for d in [*sources,*reference]],
        'rules':knowledge['rules'],'ontology':[{'relationship_id':key,'predicate':key,**value} for key,value in model['relationships'].items()],
        'counts':{**knowledge['summary'],'source_documents':len(sources)+len(reference),
            'source_entities':sum(c['kind']=='ENTITY' for c in concepts),'source_attributes':sum(c['kind']=='ATTRIBUTE' for c in concepts),
            'ontology_relationships':len(model['relationships'])},
        'catalog':{'policies':len(policies),'governed_rules':knowledge['summary']['extracted_rules'],'approved_rules':knowledge['summary']['published_rules']},
        'pipeline':knowledge['pipeline'],'ontology_version':model['version'],'knowledge_fingerprint':matcher.fingerprint}



@router.get('/taxonomy')
def taxonomy(service=Depends(get_service)):
    return [c for c in service.repo.all('taxonomy_concepts') if c.get('source',{}).get('origin')=='SOURCE_SCHEMA']


@router.get('/policy-taxonomy')
def policy_classification_taxonomy(policy_id: int | None = None):
    from ..risk_knowledge.policy_taxonomy import source_rows, build_taxonomy
    documents, entries = source_rows(shared_policy_connection)
    if policy_id is not None:
        documents = [d for d in documents if d['policy_id'] == policy_id]
        if not documents:
            raise HTTPException(404, 'Policy not found')
        entries = [c for c in entries if c['policy_id'] == policy_id]
    schema = PostgreSQLRepository(shared_policy_connection, None).all('taxonomy_concepts')
    return build_taxonomy(documents, entries, schema)


@router.get('/request-fields')
def fields(service=Depends(get_service)):
    return [c.model_dump() for c in service.taxonomy.concepts if c.status == 'APPROVED' and c.kind == 'ATTRIBUTE' and c.metadata.get('request_attribute')]


@router.post('/assets/{kind}')
async def upload(kind: Literal['schema','reference','policy'], file: UploadFile=File(), user=Depends(reviewer), service=Depends(get_service)):
    try:
        blob = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    def save():
        document = service.ingest(file.filename or 'upload', blob, kind)
        service.refresh()
        return document
    return invoke(save)


def lookup_document(identifier, service):
    if identifier.startswith('CPI-POLICY-'):
        policies, clauses, _ = catalog(service)
        item = next((d for d in documents_from_catalog(policies, clauses) if d['document_id'] == identifier), None)
    else:
        item = service.repo.get('documents', identifier)
    if item is None:
        raise HTTPException(404, 'Document not found')
    return item


@router.get('/documents/{document_id}')
def document(document_id: str, service=Depends(get_service)):
    return lookup_document(document_id, service)


@router.get('/documents/{document_id}/download')
def download(document_id: str, request: Request, service=Depends(get_service), user=Depends(current_user)):
    doc = lookup_document(document_id, service)
    registered = doc['metadata'].get('registered_path')
    if registered and doc['document_type'] == 'policy':
        path = resolve_policy_source(registered, doc['metadata'].get('original_file_name'))
    elif registered:
        path = resolve_seed_source(registered)
    else:
        path = (service.upload_dir / Path(doc['metadata']['stored_file']).name).resolve()
    if not path.is_file() or not (path.is_relative_to(BASE_DIR.resolve()) or
            path.is_relative_to(service.upload_dir.resolve()) or is_seed_policy_source(path) or
            (doc['document_type'] == 'schema' and path.parent == RISK_SCHEMA_DIR)):
        raise HTTPException(404, 'Original source file is unavailable')
    audit_export(request, user, f"risk-knowledge-document:{document_id}")
    return FileResponse(path, filename=doc['metadata'].get('original_file_name') or doc['document_name'])


@router.get('/documents/{document_id}/clauses')
def clauses(document_id: str, service=Depends(get_service)):
    if document_id.startswith('CPI-POLICY-'):
        _, entries, _ = catalog(service)
        policy_id = int(document_id.removeprefix('CPI-POLICY-'))
        classified={c['clause_id']:c for c in service.repo.all('clauses')}
        return [classified.get('CPI-CLAUSE-'+str(c['id'])) or
                {'clause_id':'CPI-CLAUSE-'+str(c['id']), 'raw_text':c['source_excerpt'], 'categories':['OTHER'],
                 'classification_method':'Existing CPI source inventory', 'source':{'clause':c['clause_number'], 'section':c['section_heading']}}
                for c in entries if c['policy_id'] == policy_id]
    return [c for c in service.repo.all('clauses') if c['document_id'] == document_id]


@router.post('/documents/{document_id}/process')
def process(document_id: str, user=Depends(reviewer), service=Depends(get_service)):
    raise HTTPException(410, 'Use the current Policy Rule Library, Policy Evidence and graph-based Compliance Review.')


@router.post('/taxonomy/enrich')
def enrich(user=Depends(reviewer), service=Depends(get_service)):
    raise HTTPException(410, 'Use the current Policy Rule Library, Policy Evidence and graph-based Compliance Review.')


@router.post('/review/{kind}/{identifier}')
def review(kind: Literal['rule','taxonomy','ontology'], identifier: str, body: Review, user=Depends(reviewer), service=Depends(get_service)):
    raise HTTPException(410, 'Use the current Policy Rule Library, Policy Evidence and graph-based Compliance Review.')


class RuleEdit(Model):
    rule: dict
    reviewer: str
    notes: str


@router.put('/rules/{rule_id}')
def edit(rule_id: str, body: RuleEdit, user=Depends(reviewer), service=Depends(get_service)):
    raise HTTPException(410, 'Use the current Policy Rule Library, Policy Evidence and graph-based Compliance Review.')


@router.get('/graph')
def graph(domain: str='', entity_type: str='', predicate: str='', source: str='', status: str='',
          focus: str='', layer: str='policy', limit: int=180, service=Depends(get_service)):
    return semantic_graph(focus=focus,limit=min(limit,6))


@router.post('/evaluate')
def evaluate(body: CreditRequest, service=Depends(get_service)):
    raise HTTPException(410, 'Use the current Policy Rule Library, Policy Evidence and graph-based Compliance Review.')


@router.get('/evaluations/{evaluation_id}')
def evaluation(evaluation_id: str, service=Depends(get_service)):
    item = service.repo.get('rule_evaluation_results', evaluation_id)
    if item is None:
        raise HTTPException(404, 'Evaluation not found for this account')
    return item


@router.post('/conflicts/{finding_id}/explain')
def conflict_explanation(finding_id: str, service=Depends(get_service)):
    match = next((f for f in service.state()['conflicts'] if f['finding_id']==finding_id), None)
    if not match:
        raise HTTPException(404, 'Finding not found')
    return invoke(lambda: service.call('conflict_explanation', match).model_dump())


@router.get('/export/{kind}')
def export(kind: Literal['rules','taxonomy','ontology','schema','example','graph','audit'], request: Request, user=Depends(current_user)):
    if kind == 'audit':
        raise HTTPException(410, 'Earlier audit records remain archived. Current rule reviews retain their own audit history.')
    report = {
        'graph': semantic_graph_export,
        'rules': semantic_knowledge,
        'ontology': business_semantic_model,
        'schema': business_semantic_schema,
        'example': business_semantic_example,
        'taxonomy': policy_classification_taxonomy,
    }[kind]()
    audit_export(request, user, f"risk-knowledge:{kind}")
    return report
