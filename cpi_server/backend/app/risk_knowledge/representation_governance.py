"""Source-bound review and verification of compiled policy graph definitions."""
from copy import deepcopy
from datetime import datetime,timezone
from typing import Literal
from fastapi import HTTPException
from pydantic import Field,model_validator
from ..database import shared_policy_connection
from ..services.inventory_schema import InventoryModel,ProposedRule
from .repositories import PostgreSQLRepository
from .policy_grammar import RequirementFrame
from .policy_representation import (representation_id,compile_graph,coverage_summary,graph_from_representation,
                                    add_requirement,digest,seal,frame_from_graph)


class SourceInterpretationReview(InventoryModel):
    representation_id: str
    content_digest: str
    span_id: str
    disposition: Literal['REQUIREMENT','NON_RULE']
    frames: list[RequirementFrame] = Field(default_factory=list,max_length=10)
    operational_severity: Literal['WARNING','BREACH'] | None = None
    notes: str = Field(min_length=3,max_length=4000)

    @model_validator(mode='after')
    def complete_disposition(self):
        if len(self.notes.strip())<3:raise ValueError('A source review needs a meaningful rationale')
        if (self.disposition=='REQUIREMENT') != bool(self.frames):
            raise ValueError('Requirements need complete frames; non-rule passages must have no frames')
        if len({digest(f.model_dump(mode='json')) for f in self.frames})!=len(self.frames):
            raise ValueError('Duplicate requirement frames')
        return self


def current_representation(policy_id):
    with shared_policy_connection() as connection:
        version=connection.execute('SELECT id,checksum FROM policy_versions WHERE policy_id=%s AND is_current',(policy_id,)).fetchone()
    if not version:raise HTTPException(404,'Current policy source not found')
    rep=PostgreSQLRepository(shared_policy_connection,None).get('metadata',representation_id(version['id'],version['checksum']))
    if not rep:raise HTTPException(404,'Build this policy representation with Extract Rules first')
    return rep


def validate_compiled_definition(row,connection,require_complete=False):
    """Recompile the authoritative graph at approval and request-selection time."""
    definition=row['definition']
    stored=connection.execute("SELECT payload FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=%s",(definition.get('representation_id'),)).fetchone()
    if not stored:raise HTTPException(409,'Source policy representation is missing; rebuild rules')
    rep=stored['payload']
    if rep['policy_id']!=row['policy_id'] or rep['policy_version_id']!=row['policy_version_id']:
        raise HTTPException(409,'Rule belongs to a different policy representation')
    version=connection.execute('SELECT checksum,is_current FROM policy_versions WHERE id=%s',(row['policy_version_id'],)).fetchone()
    if not version or not version['is_current'] or version['checksum']!=rep['source_checksum']:
        raise HTTPException(409,'Policy representation source is stale')
    clauses=connection.execute('SELECT id,source_excerpt FROM policy_clauses WHERE policy_version_id=%s ORDER BY sequence',(row['policy_version_id'],)).fetchall()
    check_definition(row,rep,clauses)
    if require_complete:
        from .rule_readiness import dependency_state,load_dependency_review
        state=dependency_state(row,rep,load_dependency_review(connection,row))
        if not state['ready']:raise HTTPException(409,'Review this rule\'s dependencies: '+'; '.join(state['blockers']))
    return True


def check_definition(row,rep,clauses,compiled=None):
    try:
        compiled=compile_graph(rep,clauses) if compiled is None else compiled
        expected=next((r.model_dump(mode='json') for r in compiled if r.representation_node_id==row['definition'].get('representation_node_id')),None)
        if expected is None:raise ValueError('Requirement is unapproved or absent from the graph')
        actual={k:v for k,v in row['definition'].items() if k!='change_rationale'}
        actual=ProposedRule.model_validate(actual).model_dump(mode='json')
        from .rule_identity import semantic_definition
        if semantic_definition(actual)!=semantic_definition(expected):raise ValueError('Stored rule differs from graph compilation')
    except ValueError as error:
        raise HTTPException(409,str(error)) from None
    return True


def review_span(policy_id,body,user):
    if user.get('role') not in ('credit_analyst','admin'):
        raise HTTPException(403,'A credit analyst or administrator must review policy interpretations')
    # Serialize read/modify/write and append reviewer evidence atomically.
    from psycopg.types.json import Jsonb
    with shared_policy_connection() as connection:
        current=connection.execute('SELECT id,checksum,effective_date FROM policy_versions WHERE policy_id=%s AND is_current FOR SHARE',(policy_id,)).fetchone()
        if not current or body.representation_id!=representation_id(current['id'],current['checksum']):
            raise HTTPException(409,'Source changed; reload the current representation')
        stored=connection.execute("SELECT payload FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=%s FOR UPDATE",(body.representation_id,)).fetchone()
        if not stored:raise HTTPException(404,'Policy representation not found')
        rep=deepcopy(stored['payload'])
        if rep['content_digest']!=body.content_digest:raise HTTPException(409,'Representation changed; reload before reviewing')
        graph=graph_from_representation(rep)
        coverage=next((r for r in rep['coverage'] if r['span_id']==body.span_id),None)
        if not coverage:raise HTTPException(422,'Select an exact source passage from this representation')
        previous_interpretations=[{'node_id':rid,'frame':frame_from_graph(graph,rid)[0].model_dump(mode='json'),
                                  'status':graph.nodes[rid]['status'],'origin':graph.nodes[rid]['payload']['origin']}
                                 for rid in coverage['requirement_ids']]
        previous_disposition=coverage['status']
        span=next(n for n in rep['nodes'] if n['id']==body.span_id)
        reviewed_at=datetime.now(timezone.utc).isoformat()
        # Replace interpretations of this span only; source span and its quote are immutable.
        roots=set(coverage['requirement_ids'])
        remove={n['id'] for n in rep['nodes'] if n['id'] in roots or any(n['id'].startswith(r+':') for r in roots)}
        rep['nodes']=[n for n in rep['nodes'] if n['id'] not in remove]
        rep['edges']=[e for e in rep['edges'] if e['source'] not in remove and e['target'] not in remove]
        coverage['requirement_ids']=[]
        from .rule_identity import source_slot
        used=set()
        for index,frame in enumerate(body.frames):
            exact=next((i for i,p in enumerate(previous_interpretations) if i not in used and p['frame']==frame.model_dump(mode='json')),None)
            prior_index=exact if exact is not None else next((i for i in range(len(previous_interpretations)) if i not in used),None)
            previous=previous_interpretations[prior_index] if prior_index is not None else None
            if prior_index is not None:used.add(prior_index)
            old_node=graph.nodes[previous['node_id']] if previous else None
            logical_key=(old_node['payload'].get('logical_rule_key') or source_slot(rep,body.span_id,prior_index)) if old_node else source_slot(rep,body.span_id,index)
            approval={'reviewer':str(user['user_id']),'reviewed_at':reviewed_at,'notes':body.notes,
                      'source_checksum':rep['source_checksum'],'frame_digest':digest(frame.model_dump(mode='json')),
                      'operational_severity':body.operational_severity}
            aliases=([previous['node_id'],*old_node['payload'].get('previous_node_ids',[])]) if previous else []
            coverage['requirement_ids'].append(add_requirement(rep,body.span_id,frame,'SOURCE_REVIEW','APPROVED',approval=approval,
                                                              logical_key=logical_key,previous_node_ids=aliases))
        coverage['status']='REVIEWED' if body.frames else 'NON_RULE'
        coverage['reason']=body.notes
        span['status']=coverage['status']
        rep['reviews'].append({'span_id':body.span_id,'disposition':body.disposition,'reviewer':str(user['user_id']),
                               'reviewed_at':reviewed_at,'notes':body.notes,'previous_digest':body.content_digest,'source_checksum':rep['source_checksum']})
        seal(rep)
        try:definitions=compile_graph(rep,rep['source_clauses'])
        except ValueError as error:raise HTTPException(422,str(error)) from None
        connection.execute("UPDATE risk_knowledge_objects SET payload=%s WHERE kind='metadata' AND owner_id='' AND id=%s",(Jsonb(rep),rep['id']))
        from .rule_identity import publish_drafts
        published,changed=publish_drafts(rep,definitions,user,connection,effective_from=current.get('effective_date'))
        connection.execute("INSERT INTO audit_events(entity_type,entity_id,previous_value,new_value,action,actor,reason) VALUES ('PolicyRepresentation',%s,%s,%s,'REVIEW_SOURCE_INTERPRETATION',%s,%s)",
            (rep['id'],Jsonb({'digest':body.content_digest,'disposition':previous_disposition,'interpretations':previous_interpretations}),Jsonb({'digest':rep['content_digest'],'review':rep['reviews'][-1],'frames':[f.model_dump(mode='json') for f in body.frames],'source_quote':span['payload']['quote']}),str(user['user_id']),body.notes))
    return {'representation':rep,'coverage':coverage_summary(rep),'requires_recompilation':False,
            'published_rule_ids':[r['id'] for r in published],'rule_versions_changed':changed,'rule_versions_unchanged':len(published)-changed}
