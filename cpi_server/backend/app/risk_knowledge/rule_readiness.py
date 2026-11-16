"""Per-rule dependency closure and a single, source-checked approval screen.

Unknown context is never silently declared irrelevant. Potential dependencies
are grouped by source clause; unrelated reporting/background is not a gate.
"""
import re
from copy import deepcopy
from datetime import datetime,timezone
from typing import Literal
from fastapi import HTTPException
from pydantic import Field
from ..services.inventory_schema import InventoryModel,Condition
from .policy_representation import digest,compile_graph,coverage_summary,representation_id,graph_from_representation,frame_from_graph
from .rule_identity import semantic_digest

DEPENDENCY_VERSION='rule-dependencies-v1'


class DependencyResolution(InventoryModel):
    dependency_id: str
    disposition: Literal['covered','not_applicable','needs_work']
    rationale: str = Field(min_length=3,max_length=4000)
    conditions: Condition | None = None
    exclusions: Condition | None = None


class RuleApproval(InventoryModel):
    review_token: str
    dependency_digest: str
    resolutions: list[DependencyResolution] = Field(default_factory=list,max_length=200)
    severity: Literal['WARNING','BREACH']
    data_source: str = Field(min_length=3,max_length=2000)
    comment: str = Field(min_length=3,max_length=4000)
    confirmed: Literal[True]


def dependency_key(row):
    return 'RULE-DEPENDENCIES-'+row['rule_key']


def load_dependency_review(connection,row):
    stored=connection.execute("SELECT payload FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=%s",(dependency_key(row),)).fetchone()
    return stored['payload'] if stored else None


def clause_role(clause):
    text=clause.get('section_heading') or clause['source_excerpt'][:150]
    match=re.match(r'\s*(?:\d+[.)]?\s*)*(Purpose|Scope|Definitions?|Governance|Underwriting Criteria|Quantitative Limits|Approvals?|Exceptions?|Monitoring|Reporting|Review)\b',text,re.I)
    if match:return match[1].lower()
    if re.match(r'\s*(?:monthly|quarterly|annual) reports\b',text,re.I):return 'reporting'
    return ''


def dependency_candidates(row,rep):
    """Conservative context selection, independent of coverage classification changes."""
    from .policy_ontology import METRICS
    from .policy_grammar import normalized_text,classify_non_rule
    definition=row['definition']
    metric_key=next((key for key,m in METRICS.items() if m['field']==(definition.get('calculation_logic') or {}).get('field')),None)
    terms=METRICS.get(metric_key,{}).get('terms',[])
    items=[]
    for clause in rep['source_clauses']:
        text=normalized_text(clause['source_excerpt']);lower=text.lower();role=clause_role(clause)
        if classify_non_rule(clause['source_excerpt']):continue
        metric=any(re.search(r'(?<![a-z])'+re.escape(term)+r'(?![a-z])',lower) for term in terms)
        scope=bool(re.search(r'\b(?:applies to|apply to|does not apply|excludes|binding for)\b',lower))
        override=bool(re.search(r'\b(?:stricter|override|takes precedence|supersedes|unless|exempt)\b',lower))
        numeric_change=metric and bool(re.search(r'\b(?:must not exceed|shall not exceed|reduced to|maximum|minimum|ceiling of)\b[^.!?]*\d+(?:\.\d+)?\s*(?:%|x|years?)',lower))
        if role in ('monitoring','reporting','review') and not (scope or override or numeric_change):continue
        if role=='purpose' and not (scope or override or numeric_change):continue
        if role in ('scope','definition','definitions') or scope:kind='Scope and definitions'
        elif role in ('exception','exceptions','approval','approvals') or override:kind='Exceptions, overrides and approvals'
        elif metric and role in ('underwriting criteria','quantitative limits','governance'):kind='Related requirements and conditions'
        elif not role:kind='Unclassified source context'
        elif metric and numeric_change:kind='Potential related limit'
        else:continue
        # A clause containing only this completely represented requirement has
        # no additional dependency to review. Other/unknown context is retained.
        source=normalized_text(definition['source_excerpt'])
        if text==source:continue
        identifier='DEPENDENCY-'+digest([rep['policy_version_id'],clause['id'],kind])[:24]
        items.append({'id':identifier,'clause_id':clause['id'],'kind':kind,
                      'label':(role.title() if role else 'Source context')+' — clause '+str(clause.get('clause_number') or clause.get('sequence') or clause['id']),
                      'source_excerpt':clause['source_excerpt'],'page':clause.get('page_number'),
                      'reason':'This source section may affect this rule; confirm its effect rather than clearing every passage.'})
    return items


def dependency_snapshot(row,rep):
    items=dependency_candidates(row,rep)
    graph=graph_from_representation(rep)
    for item in items:
        facts=[]
        for coverage in rep['coverage']:
            if coverage['clause_id']!=item['clause_id']:continue
            for rid in coverage['requirement_ids']:
                if graph.nodes[rid]['status'] not in ('VALIDATED','APPROVED'):continue
                frame,_=frame_from_graph(graph,rid)
                scope=frame.scope.model_dump(mode='json') if frame.scope else None
                if scopes_disjoint(row['definition'].get('applicability_conditions'),scope):continue
                facts.append({'source_span':coverage['span_id'],'meaning':frame.model_dump(mode='json')})
        item['graph_facts']=sorted(facts,key=digest)
    return {'items':items,'digest':digest([DEPENDENCY_VERSION,rep['source_checksum'],semantic_digest(row['definition']),items])}


def scopes_disjoint(left,right):
    """Prove disjointness only from explicit equality/membership alternatives.

    Unknown operators/large expressions never establish disjointness.
    """
    from ..services.credit_data import ALIASES
    def branches(condition):
        if not condition:return [{}]
        if condition.get('any'):
            result=[]
            for child in condition['any']:
                values=branches(child)
                if values is None:return None
                result+=values
            return result if len(result)<=32 else None
        if condition.get('all'):
            result=[{}]
            for child in condition['all']:
                values=branches(child)
                if values is None or len(result)*len(values)>32:return None
                merged=[]
                for a in result:
                    for b in values:
                        value={k:set(v) for k,v in a.items()}
                        for field,allowed in b.items():value[field]=value[field]&allowed if field in value else set(allowed)
                        merged.append(value)
                result=merged
            return result
        if condition.get('operator') not in ('equals','in_list'):return [{}]
        values=condition['value'] if condition['operator']=='in_list' else [condition['value']]
        return [{ALIASES.get(condition['field'],condition['field']):{digest(v) for v in values}}]
    a,b=branches(left),branches(right)
    if a is None or b is None:return False
    return all(any(not x[field]&y[field] for field in x.keys()&y.keys()) for x in a for y in b)


def dependency_state(row,rep,review=None):
    snapshot=dependency_snapshot(row,rep)
    valid=bool(review and review.get('snapshot_digest')==snapshot['digest'] and review.get('reviewer')
               and review.get('source_checksum')==rep['source_checksum'])
    saved={r['dependency_id']:r for r in review.get('resolutions',[])} if valid else {}
    blockers=[]
    for item in snapshot['items']:
        resolution=saved.get(item['id'])
        if not resolution or resolution['disposition']=='needs_work' or len(resolution.get('rationale','').strip())<3:
            blockers.append(item['label'])
    return {**snapshot,'ready':not blockers,'blockers':blockers,'resolutions':list(saved.values()),'review_current':valid}


def validate_guard(condition,source):
    from ..services.credit_data import GROUPS,ALIASES
    from .policy_ontology import SCOPE_FIELDS,SCOPE_VOCABULARIES,FACILITIES
    known=set(GROUPS)|set(ALIASES)|SCOPE_FIELDS
    if not condition:return
    if condition.field:
        if condition.field not in known:raise HTTPException(422,'Declare an input binding before using dependency field '+condition.field)
        values=condition.value if isinstance(condition.value,list) else [condition.value]
        for value in values:
            if value is None or isinstance(value,bool):continue
            if isinstance(value,(float,int)):
                stated={float(n.replace(',','')) for n in re.findall(r'\d[\d,]*(?:\.\d+)?',source)}
                if value not in stated:raise HTTPException(422,'Dependency guard threshold is absent from its source')
            else:
                terms=SCOPE_VOCABULARIES.get(condition.field,{}).get(value,[str(value)])
                if condition.field=='facility':terms=[term for term,canonical in FACILITIES.items() if canonical==value]
                if not any(' '.join(term.lower().split()) in ' '.join(source.lower().split()) for term in terms):
                    raise HTTPException(422,'Dependency guard value is absent from its source')
    for group in (condition.all,condition.any):
        for child in group or []:validate_guard(child,source)


def effective_rule(row,review=None):
    review=review or row.get('_dependency_review')
    result=deepcopy(row)
    if not review:return result
    definition=result['definition'];conditions=[];exclusions=[]
    if definition.get('applicability_conditions'):conditions.append(definition['applicability_conditions'])
    if definition.get('applicability_exclusions'):exclusions.append(definition['applicability_exclusions'])
    for item in review.get('resolutions',[]):
        if item.get('conditions'):conditions.append(item['conditions'])
        if item.get('exclusions'):exclusions.append(item['exclusions'])
    if conditions:definition['applicability_conditions']=conditions[0] if len(conditions)==1 else {'all':conditions}
    if exclusions:definition['applicability_exclusions']=exclusions[0] if len(exclusions)==1 else {'any':exclusions}
    return result


def inspect_rule(row,rep,clauses,review=None,compiled=None):
    from .representation_governance import check_definition
    checks=[]
    def add(key,ok,message):checks.append({'key':key,'status':'pass' if ok else 'blocked','message':message})
    try:check_definition(row,rep,clauses,compiled=compiled);source_ok=True
    except HTTPException as error:source_ok=False;source_message=error.detail
    add('source',source_ok,'Rule matches its current source graph' if source_ok else source_message)
    dependencies=dependency_state(row,rep,review)
    add('dependencies',dependencies['ready'],'Relevant source dependencies reviewed' if dependencies['ready'] else f"{len(dependencies['blockers'])} relevant source sections need a decision")
    add('data_source',bool(row['definition'].get('data_source')),'Actual input data source assigned' if row['definition'].get('data_source') else 'Assign the actual input data source')
    add('severity',row['definition'].get('severity') in ('WARNING','BREACH'),'Operational severity assigned' if row['definition'].get('severity') else 'Choose the outcome when this rule fails')
    add('effective_date',bool(row.get('effective_from')),'Effective date recorded' if row.get('effective_from') else 'Confirm the effective date')
    coverage=coverage_summary(rep)
    return {'rule_id':row['id'],'version':row['version'],'status':row['status'],'checks':checks,
            'structurally_current':source_ok,'can_approve':all(c['status']=='pass' for c in checks),
            'blockers':[c['message'] for c in checks if c['status']=='blocked'],
            'dependencies':dependencies,'coverage':coverage,'requires_whole_policy_resolution':False,
            'review_token':digest([row['id'],row['version'],row['status'],row['definition'],rep['source_checksum'],dependencies['digest']])}


def get_readiness(rule_id,connection):
    row=connection.execute('SELECT * FROM policy_rule_versions WHERE id=%s',(rule_id,)).fetchone()
    if not row:raise HTTPException(404,'Rule not found')
    if not row['definition'].get('representation_id'):raise HTTPException(409,'Historical extraction: rebuild from the source graph before operational approval')
    from .representation_governance import validate_compiled_definition
    validate_compiled_definition(row,connection)
    rep=connection.execute("SELECT payload FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=%s",(row['definition']['representation_id'],)).fetchone()['payload']
    clauses=connection.execute('SELECT id,source_excerpt FROM policy_clauses WHERE policy_version_id=%s ORDER BY sequence',(row['policy_version_id'],)).fetchall()
    return row,rep,inspect_rule(row,rep,clauses,load_dependency_review(connection,row))


def approve_rule(rule_id,body,user):
    from ..database import shared_policy_connection
    from ..services.rule_governance import reviewer,audit,children,approval_ready
    from psycopg.types.json import Jsonb
    reviewer(user)
    with shared_policy_connection() as connection:
        reference=connection.execute('SELECT rule_key,definition FROM policy_rule_versions WHERE id=%s',(rule_id,)).fetchone()
        if not reference:raise HTTPException(404,'Rule not found')
        locked=connection.execute("SELECT payload FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=%s FOR SHARE",(reference['definition'].get('representation_id'),)).fetchone()
        if not locked:raise HTTPException(409,'Build the source representation before reviewing this rule')
        connection.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(reference['rule_key'],))
        row,rep,readiness=get_readiness(rule_id,connection)
        # Lock the source representation before rechecking its meaning.
        if locked['payload']['content_digest']!=rep['content_digest']:raise HTTPException(409,'Interpretation changed; reload this review')
        row=connection.execute('SELECT * FROM policy_rule_versions WHERE id=%s FOR UPDATE',(rule_id,)).fetchone()
        if row['status'] not in ('Draft','Under Review','Approved','Active'):raise HTTPException(409,'This rule status cannot be approved from the review screen')
        if body.review_token!=readiness['review_token'] or body.dependency_digest!=readiness['dependencies']['digest']:
            raise HTTPException(409,'Rule or dependencies changed; reload the checklist')
        latest=connection.execute('SELECT id FROM policy_rule_versions WHERE rule_key=%s ORDER BY version DESC LIMIT 1',(row['rule_key'],)).fetchone()
        if latest['id']!=rule_id:raise HTTPException(409,'A newer rule version exists; review that version')
        resolutions={r.dependency_id:r for r in body.resolutions}
        items=readiness['dependencies']['items']
        if len(resolutions)!=len(body.resolutions) or set(resolutions)!={i['id'] for i in items}:
            raise HTTPException(422,'Record one decision for each relevant dependency section')
        for item in items:
            resolution=resolutions[item['id']]
            if resolution.disposition=='needs_work' or len(resolution.rationale.strip())<3:
                raise HTTPException(409,'Dependency still needs work: '+item['label'])
            validate_guard(resolution.conditions,item['source_excerpt']);validate_guard(resolution.exclusions,item['source_excerpt'])
        if len(body.comment.strip())<3 or len(body.data_source.strip())<3:raise HTTPException(422,'Provide a meaningful review rationale and data source')
        definition=deepcopy(row['definition'])
        definition.update(severity=body.severity,data_source=body.data_source.strip())
        if row['status'] in ('Approved','Active'):
            # Never rewrite an approved definition that historical assessments
            # may reference. A deliberate re-review creates one approved revision.
            from ..services.inventory_schema import GovernedDefinition,GovernedRuleInput
            from ..services.rule_governance import store_rule
            from uuid import uuid4
            values={k:v for k,v in definition.items() if k!='change_rationale'}
            governed=GovernedDefinition(**values,change_rationale='Explicit governance and dependency re-review; prior approved snapshot preserved')
            row=store_rule(GovernedRuleInput(policy_id=row['policy_id'],definition=governed,effective_from=row['effective_from'],effective_to=row.get('effective_to')),
                           user,previous=rule_id,extraction_key='graph-first:review:'+str(uuid4()),c=connection,force_draft=True)
            rule_id=row['id']
            definition=row['definition']
        before=deepcopy(dict(row))
        dependency_review={'kind':'rule_dependency_review','rule_key':row['rule_key'],'rule_version_id':rule_id,
                           'source_checksum':rep['source_checksum'],'snapshot_digest':body.dependency_digest,
                           'reviewer':str(user['user_id']),'reviewed_at':datetime.now(timezone.utc).isoformat(),
                           'resolutions':[r.model_dump(mode='json') for r in body.resolutions]}
        connection.execute('''INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES ('metadata','',%s,%s)
            ON CONFLICT(kind,owner_id,id) DO UPDATE SET payload=EXCLUDED.payload''',(dependency_key(row),Jsonb(dependency_review)))
        row={**row,'definition':definition}
        approval_ready(row,connection)
        source=connection.execute('''SELECT pv.is_current,pv.version,p.status AS policy_status,md5(p.summary) AS fingerprint
            FROM policy_versions pv JOIN policy_documents p ON p.policy_id=pv.policy_id WHERE pv.id=%s FOR SHARE OF pv,p''',(row['policy_version_id'],)).fetchone()
        if not source or not source['is_current'] or source['policy_status'].lower()!='active' or source['version']!=row['policy_version'] or source['fingerprint']!=row['policy_fingerprint']:
            raise HTTPException(409,'Underlying policy changed; rebuild its source representation')
        predecessors=connection.execute("SELECT * FROM policy_rule_versions WHERE rule_key=%s AND id<>%s AND status='Active' FOR UPDATE",(row['rule_key'],rule_id)).fetchall()
        for previous in predecessors:
            inactive=connection.execute("UPDATE policy_rule_versions SET status='Inactive',active=false WHERE id=%s RETURNING *",(previous['id'],)).fetchone()
            audit(connection,previous,inactive,user,'superseded by approved revision',body.comment)
        approved=connection.execute("""UPDATE policy_rule_versions SET definition=%s,status='Approved',active=false,
            reviewed_by=%s,reviewed_at=CURRENT_TIMESTAMP,review_comments=%s,approved_by=%s,approval_date=CURRENT_TIMESTAMP,
            approval_decision='approve' WHERE id=%s RETURNING *""",(Jsonb(definition),user['user_id'],body.comment.strip(),user['user_id'],rule_id)).fetchone()
        children(connection,approved)
        connection.execute("INSERT INTO rule_reviews(rule_version_id,reviewed_by,decision,comments) VALUES (%s,%s,'approve',%s)",(rule_id,user['user_id'],body.comment.strip()))
        audit(connection,before,approved,user,'approve with dependency review',body.comment.strip())
        annotation={'pipeline':'policy-graph-first-v1','status':'GRAPH_COMPILED_APPROVED','representation_id':rep['id'],
                    'representation_node_id':definition['representation_node_id'],'dependency_snapshot_digest':body.dependency_digest,
                    'definition_fingerprint':digest(definition),'validation':{'source_provenance_verified':True,'graph_compilation_verified':True},
                    'source':next(n['provenance'] for n in rep['nodes'] if n['id']==definition['representation_node_id'])}
        connection.execute("""INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES ('metadata','',%s,%s)
            ON CONFLICT(kind,owner_id,id) DO UPDATE SET payload=risk_knowledge_objects.payload||EXCLUDED.payload""",('CPI-RULE-'+str(rule_id),Jsonb(annotation)))
        connection.execute("INSERT INTO audit_events(entity_type,entity_id,new_value,action,actor,reason) VALUES ('RuleDependencies',%s,%s,'REVIEW_DEPENDENCIES',%s,%s)",(str(rule_id),Jsonb(dependency_review),user['user_id'],body.comment.strip()))
    return {'rule':dict(approved),'dependency_review':dependency_review,'policy_coverage_complete':readiness['coverage']['complete']}
