"""Explicit reviewer approval of version-bound, source-backed policy scope."""
from datetime import datetime, timezone
from fastapi import HTTPException
from pydantic import Field, model_validator
from .inventory_schema import InventoryModel, Condition
from ..database import shared_policy_connection
from ..risk_knowledge.repositories import PostgreSQLRepository


class PolicyScopeInput(InventoryModel):
    policy_version_id: int = Field(gt=0)
    clause_id: int = Field(gt=0)
    source_excerpt: str = Field(min_length=1, max_length=16000)
    conditions: Condition | None = None
    exclusions: Condition | None = None
    unrestricted: bool = False
    notes: str = Field(min_length=3, max_length=2000)

    @model_validator(mode='after')
    def scope_required(self):
        if self.unrestricted == (self.conditions is not None):
            raise ValueError('Specify inclusion conditions or explicitly confirm unrestricted scope')
        return self


def scope_context(policy_id):
    with shared_policy_connection() as db:
        version = db.execute('''SELECT pv.id,pv.policy_id,pv.checksum,pv.version,p.title
            FROM policy_versions pv JOIN policy_documents p USING(policy_id)
            WHERE pv.policy_id=%s AND pv.is_current''', (policy_id,)).fetchone()
        if not version:
            raise HTTPException(404, 'Current policy version not found')
        clauses = db.execute('''SELECT id,clause_number,section_heading,source_excerpt
            FROM policy_clauses WHERE policy_version_id=%s ORDER BY sequence''', (version['id'],)).fetchall()
    saved = PostgreSQLRepository(shared_policy_connection, None).get('metadata', 'CPI-POLICY-SCOPE-' + str(policy_id))
    return {'policy': version, 'clauses': clauses, 'scope': saved}


def approve_scope(policy_id, body, user):
    if user['role'] not in ('credit_analyst', 'admin'):
        raise HTTPException(403, 'A credit analyst or administrator must approve policy scope')
    context = scope_context(policy_id)
    policy = context['policy']
    if body.policy_version_id != policy['id']:
        raise HTTPException(409, 'Policy source changed; reload and review the current version')
    clause = next((c for c in context['clauses'] if c['id'] == body.clause_id), None)
    if not clause or not body.source_excerpt.strip() or body.source_excerpt not in clause['source_excerpt']:
        raise HTTPException(422, 'An exact passage from a clause in this policy version is required')
    record = {**body.model_dump(), 'kind': 'policy_scope', 'policy_id': policy_id,
              'source_checksum': policy['checksum'], 'status': 'APPROVED',
              'approved_by': str(user['user_id']), 'approved_at': datetime.now(timezone.utc).isoformat(),
              'source': {'document_id': 'CPI-POLICY-' + str(policy_id), 'document_name': policy['title'],
                         'origin': 'REVIEWED_POLICY_SCOPE', 'passage': body.source_excerpt,
                         'version': policy['version'], 'clause': clause.get('clause_number')}}
    # Repository writes the scope and reviewer audit in the same transaction.
    PostgreSQLRepository(shared_policy_connection, user['user_id']).put(
        'metadata', 'CPI-POLICY-SCOPE-' + str(policy_id), record,
        {'entity_id': policy_id, 'action': 'APPROVE_POLICY_SCOPE', 'notes': body.notes,
         'previous_scope': context['scope'], 'approved_scope': record})
    return record
