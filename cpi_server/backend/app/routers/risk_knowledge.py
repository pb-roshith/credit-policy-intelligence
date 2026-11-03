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

router = APIRouter(prefix='/api/risk-knowledge', tags=['Risk Knowledge'], dependencies=[Depends(current_user)])
lock = RLock()


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
    result = invoke(service.state)
    policies, clauses, rules = catalog(service)
    documents = documents_from_catalog(policies, clauses)
    combined={d['document_id']:d for d in result['documents']}
    for document in documents:
        combined.setdefault(document['document_id'],{k:v for k,v in document.items() if k!='raw_text'})
    result['documents']=list(combined.values())
    result['counts']['source_documents'] = len(result['documents'])
    result['catalog'] = {'policies': len(policies), 'governed_rules': len(rules),
                         'approved_rules': sum(r['status'] in ('Approved','Active') and not r['review_required'] for r in rules)}
    return result


@router.get('/taxonomy')
def taxonomy(service=Depends(get_service)):
    return service.repo.all('taxonomy_concepts')


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
    if document_id.startswith('CPI-POLICY-'):
        raise HTTPException(422, 'Use Extract Rules in Policy Rule Library to run the Risk Knowledge pipeline')
    return invoke(lambda: service.process(document_id))


@router.post('/taxonomy/enrich')
def enrich(user=Depends(reviewer), service=Depends(get_service)):
    return invoke(service.enrich)


@router.post('/review/{kind}/{identifier}')
def review(kind: Literal['rule','taxonomy','ontology'], identifier: str, body: Review, user=Depends(reviewer), service=Depends(get_service)):
    return invoke(lambda: service.review(kind, identifier, body.status, user['user_id'], body.notes))


class RuleEdit(Model):
    rule: dict
    reviewer: str
    notes: str


@router.put('/rules/{rule_id}')
def edit(rule_id: str, body: RuleEdit, user=Depends(reviewer), service=Depends(get_service)):
    if len(body.notes.strip()) < 3:
        raise HTTPException(422, 'Edit notes are required')
    return invoke(lambda: service.edit_rule(rule_id, body.rule, user['user_id'], body.notes))


@router.get('/graph')
def graph(domain: str='', entity_type: str='', predicate: str='', source: str='', status: str='',
          focus: str='', layer: str='policy', limit: int=180, service=Depends(get_service)):
    if layer != 'ontology':
        project_catalog(service.graph, *catalog(service))
    snapshot = service.graph.snapshot()
    nodes, edges = snapshot['nodes'], snapshot['edges']
    if focus:
        keep = service.graph.neighborhood(focus, depth=2)
        nodes = [n for n in nodes if n['id'] in keep]
    elif layer == 'ontology':
        endpoints = {r[k] for r in service.repo.all('ontology_relationships') for k in ('subject','object')}
        nodes = [n for n in nodes if n['id'] in endpoints]
    else:
        nodes = [n for n in nodes if n['provenance'] and n['provenance']['origin'] not in ('SOURCE_SCHEMA','AI_PROPOSED')]
    nodes = [n for n in nodes if (not domain or n['risk_domain']==domain) and (not entity_type or n['type']==entity_type)
             and (not source or source.lower() in (n['source_name'] or '').lower()) and (not status or n['status']==status)]
    if predicate:
        related = {e[k] for e in edges if e['predicate']==predicate for k in ('source','target')}
        nodes = [n for n in nodes if n['id'] in related]
    total = len(nodes)
    # Budget complete rule neighborhoods so a truncated graph still shows evidence edges.
    if not focus and layer != 'ontology':
        available = {n['id']:n for n in nodes}
        selected = []
        selected_ids = set()
        budget = max(1,min(limit,500))
        for root in [n for n in nodes if n['type'] in ('GovernedPolicyRule','PolicyRule')]:
            neighbors = {root['id']} | {e['target'] for e in edges if e['source']==root['id']} | {e['source'] for e in edges if e['target']==root['id']}
            neighbors |= {e['source'] for e in edges if e['target'] in neighbors and e['predicate']=='CONTAINS' and available.get(e['source'],{}).get('type')=='PolicyDocument'}
            bundle = [available[k] for k in neighbors if k in available and k not in selected_ids]
            if len(selected)+len(bundle)>budget:
                continue
            selected += bundle
            selected_ids.update(n['id'] for n in bundle)
        nodes = selected + [n for n in nodes if n['id'] not in selected_ids]
    nodes = nodes[:max(1,min(limit,500))]
    ids = {n['id'] for n in nodes}
    edges = [e for e in edges if e['source'] in ids and e['target'] in ids and (not predicate or e['predicate']==predicate)
             and (not status or e['status']==status)]
    return {'nodes':nodes, 'edges':edges, 'total_nodes':total, 'truncated':len(nodes)<total}


@router.post('/evaluate')
def evaluate(body: CreditRequest, service=Depends(get_service)):
    return invoke(lambda: service.evaluate(body.model_dump()))


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
    if kind == 'graph':
        project_catalog(service.graph, *catalog(service))
        return service.graph.snapshot()
    if kind == 'audit':
        return service.repo.audit()
    return service.repo.all({'rules':'policy_rules','taxonomy':'taxonomy_concepts','ontology':'ontology_relationships'}[kind])
