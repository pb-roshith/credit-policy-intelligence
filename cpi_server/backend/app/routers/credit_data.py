"""All ingestion paths use the same canonical record contract."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from ..security import current_user
from ..database import db_connection, shared_policy_connection
from ..services.credit_data import load_record, store_record, sync_registry, coverage_report, resolve_actual, synthetic_record
from ..services.rule_assessment import active_rule_candidates, assessment_request_context

router = APIRouter(prefix='/api/credit-data', tags=['credit data and evidence'])


def request_exists(request_id):
    # Resolves account-owned CPI and shared Dossier requests through existing access checks.
    if request_id.startswith('CR-'):
        with db_connection() as c:
            if not c.execute('SELECT 1 FROM credit_requests WHERE credit_request_number=%s', (request_id,)).fetchone():
                raise HTTPException(404, 'Credit request not found')


@router.get('/registry')
def registry(_: dict = Depends(current_user)):
    rules = active_rule_candidates(date.today())
    attributes, mappings = sync_registry(rules)
    return {'attributes': attributes, 'rule_mappings': mappings, 'rule_count': len(rules)}


@router.get('/requests/{request_id}')
def get_data(request_id: str, _: dict = Depends(current_user)):
    record = load_record(request_id)
    if record is None: raise HTTPException(404, 'Canonical credit data has not been populated')
    return record


@router.put('/requests/{request_id}')
def ingest_data(request_id: str, payload: dict, user: dict = Depends(current_user)):
    if payload.get('request_id') != request_id: raise HTTPException(422, 'Request identity mismatch')
    if request_id.startswith('CR-'): request_exists(request_id)
    else: assessment_request_context(request_id, user)
    try: store_record(payload, payload.get('revision', 0))
    except (ValueError, KeyError, TypeError) as error: raise HTTPException(422, str(error)) from error
    return load_record(request_id)


@router.get('/requests/{request_id}/coverage')
def coverage(request_id: str, _: dict = Depends(current_user)):
    record = load_record(request_id)
    if record is None: raise HTTPException(404, 'Canonical credit data has not been populated')
    return coverage_report(active_rule_candidates(date.today()), record)


@router.get('/requests/{request_id}/resolve/{rule_version_id}')
def resolve(request_id: str, rule_version_id: int, entity_id: str | None = None, period: str | None = None, _: dict = Depends(current_user)):
    record = load_record(request_id)
    if record is None: raise HTTPException(404, 'Canonical credit data has not been populated')
    rule = next((r for r in active_rule_candidates(date.today()) if r['id']==rule_version_id), None)
    if rule is None: raise HTTPException(404, 'Current rule version not found')
    return resolve_actual(rule, record, entity_id=entity_id, period=period)


@router.post('/manufacture-existing')
def manufacture_existing(user: dict = Depends(current_user)):
    rules = active_rule_candidates(date.today()); sync_registry(rules)
    with db_connection() as c:
        requests = c.execute("SELECT * FROM credit_requests WHERE shared_deal_id IS NULL ORDER BY credit_request_number").fetchall()
    scenarios = ['compliant', 'boundary', 'breach', 'multiple_breaches', 'missing', 'conflicting', 'warning', 'near_threshold']
    count = 0
    for index, proposal in enumerate(requests):
        if load_record(proposal['credit_request_number']): continue
        store_record(synthetic_record(dict(proposal), rules, scenarios[index % len(scenarios)])); count += 1
    return {'created': count, 'existing_requests': len(requests), 'label': 'Manufactured Demonstration Data'}
