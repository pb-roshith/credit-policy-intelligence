"""Authenticated extension of the existing CPI API, not a second application."""
import os
from datetime import date
from pathlib import Path
from threading import RLock
from typing import Literal
from xml.etree.ElementTree import ParseError
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import Field
from fastapi.responses import FileResponse
from pypdf.errors import PdfReadError
from openpyxl.utils.exceptions import InvalidFileException
from ..config import BASE_DIR
from ..database import shared_policy_connection
from ..security import current_user
from ..risk_knowledge.catalog import read_catalog, documents_from_catalog, project_catalog
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
def export_semantic_knowledge():
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
    if user['role'] not in ('credit_analyst','admin'):raise HTTPException(403,'A credit analyst or administrator must review scope')
    from ..risk_knowledge.semantic_scope import review_scope
    return invoke(lambda:review_scope(semantic_repository(),policy_id,body.expected_digest,body.scope,body.status,user['user_id'],body.notes))


@router.post('/semantic-rules/review')
def semantic_rule_review(body: SemanticReview, user=Depends(current_user)):
    if user['role'] not in ('credit_analyst','admin'):
        raise HTTPException(403,'A credit analyst or administrator must override extracted knowledge')
    from ..risk_knowledge.semantic_pipeline import review_rule
    return invoke(lambda: review_rule(semantic_repository(),body.rule_id,status=body.status,
        notes=body.notes,actor=user['user_id'],expected_digest=body.expected_digest,replacement=body.replacement))


@router.get('/semantic-model/schema')
def business_semantic_schema():
    from ..risk_knowledge.semantic_model import instance_schema
    return instance_schema()


@router.get('/semantic-model/ontology.ttl')
def business_semantic_owl():
    from fastapi.responses import Response
    from ..risk_knowledge.semantic_rdf import ontology_graph
    return Response(ontology_graph().serialize(format='turtle'), media_type='text/turtle')


@router.get('/semantic-model/shapes.ttl')
def business_semantic_shapes():
    from fastapi.responses import Response
    from ..risk_knowledge.semantic_rdf import shapes_graph
    return Response(shapes_graph().serialize(format='turtle'), media_type='text/turtle')


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
def request_graph(request_id: str, focus: str = '', user=Depends(current_user)):
    from ..services.rule_assessment import assessment_request_context
    from ..services.semantic_matching import load_matcher
    from ..risk_knowledge.semantic_view import graph_view
    _,data=assessment_request_context(request_id,user)
    matcher=load_matcher();report=matcher.match(data)
    graph=invoke(lambda:graph_view(matcher.records,focus=focus))
    decisions={d['candidate_id']:d for d in report['decisions'] if d['candidate_type']=='Rule'}
    graph['nodes']=[{**n,'applicability':decisions.get(n['id'],{}).get('applicability')} for n in graph['nodes']]
    return {**graph,'report':report,'knowledge_fingerprint':matcher.fingerprint}



def invoke(operation):
    try:
        with lock:
            return operation()
    except KeyError:
        raise HTTPException(404, 'Risk knowledge object not found') from None
    except (ValueError, PdfReadError, ParseError, InvalidFileException) as error:
        raise HTTPException(422, str(error)) from None


def reviewer(user=Depends(current_user)):
    if user['role'] not in ('credit_analyst', 'admin'):
        raise HTTPException(403, 'A credit analyst or administrator must review or change risk knowledge')
    return user


def get_service(user=Depends(current_user)):
    service = IntelligenceService(repository=PostgreSQLRepository(shared_policy_connection, user['user_id']))
    path = os.getenv('CPI_RISK_SCHEMA_PATH') or str(BASE_DIR / 'risk_schema' / 'Risk Data Model_Oct 2026.xlsx')
    invoke(lambda: service.bootstrap(path))
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
    from ..services.rule_extraction import run_inventory_job
    if user['role'] not in ('relationship_manager','credit_analyst','admin'):
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
        if user['role']=='relationship_manager' and job['created_by']!=user['user_id']:
            raise HTTPException(403,'You can retry your own extraction jobs')
        if c.execute("SELECT 1 FROM rule_inventory_jobs WHERE status IN ('Queued','Running')").fetchone():
            raise HTTPException(409,'An extraction is already running')
        job=c.execute("UPDATE rule_inventory_jobs SET status='Queued',error=NULL,finished_at=NULL,heartbeat_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *",(job_id,)).fetchone()
    background.add_task(run_inventory_job,job_id,user)
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
    blob = await file.read(MAX_BYTES + 1)
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
def download(document_id: str, service=Depends(get_service)):
    doc = lookup_document(document_id, service)
    registered = doc['metadata'].get('registered_path')
    path = Path(registered).resolve() if registered else (service.upload_dir / Path(doc['metadata']['stored_file']).name).resolve()
    if not path.is_relative_to(BASE_DIR.resolve()) or not path.is_file():
        # Isolated dependency-overridden tests use their own upload directory.
        if not path.is_relative_to(service.upload_dir.resolve()) or not path.is_file():
            raise HTTPException(404, 'Original source file is unavailable')
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
def export(kind: Literal['rules','taxonomy','ontology','graph','audit'], service=Depends(get_service)):
    if kind == 'graph': return export_semantic_knowledge()
    if kind == 'rules': return semantic_knowledge()
    if kind == 'ontology': return business_semantic_model()
    if kind == 'taxonomy': return policy_classification_taxonomy()
    raise HTTPException(410, 'Earlier audit records remain archived. Current rule reviews retain their own audit history.')
