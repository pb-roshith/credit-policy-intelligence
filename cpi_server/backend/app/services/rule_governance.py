"""Inventory persistence and human governance in one transaction per change."""
import hashlib
import json
from datetime import date
from uuid import uuid4
from fastapi import HTTPException
from ..database import shared_policy_connection
from .inventory_schema import GovernedRuleInput


def reviewer(user):
    if user.get('role') not in ('credit_analyst','admin'):
        raise HTTPException(403,'A credit analyst or administrator must review rules')


def audit(c, before, after, user, action, reason):
    c.execute('INSERT INTO audit_events(entity_type,entity_id,previous_value,new_value,action,actor,reason) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)',('PolicyRuleVersion',str(after['id']),json.dumps(before,default=str) if before else None,json.dumps(after,default=str),action,user['user_id'],reason))
    c.execute('INSERT INTO policy_rule_audit(rule_id,actor,action,comment,snapshot) VALUES (%s,%s,%s,%s,%s::jsonb)',(after['id'],user['user_id'],action,reason,json.dumps(after,default=str)))


def children(c,row):
    d=row['definition']; rid=row['id']
    for table in ('rule_applicability_conditions','rule_input_requirements','rule_evidence_requirements'):
        c.execute(f'DELETE FROM {table} WHERE rule_version_id=%s',(rid,))
    if d.get('applicability_conditions'):
        c.execute('INSERT INTO rule_applicability_conditions(rule_version_id,sequence,condition) VALUES (%s,1,%s::jsonb)',(rid,json.dumps(d['applicability_conditions'])))
    if d.get('applicable_stage'):
        c.execute('INSERT INTO rule_applicability_conditions(rule_version_id,sequence,condition) VALUES (%s,2,%s::jsonb)',(rid,json.dumps({'field':'status','operator':'in_list','value':d['applicable_stage']})))
    from .rule_engine import referenced_fields
    for field in referenced_fields(d):
        definition=next((item for item in d.get('input_field_definitions',[]) if item.get('field_name')==field),{})
        c.execute('INSERT INTO rule_input_requirements(rule_version_id,field_name,data_source,field_definition,field_unit,required) VALUES (%s,%s,%s,%s,%s,%s)',(rid,field,d.get('data_source'),definition.get('definition'),definition.get('unit'),definition.get('required',True)))
    for requirement in d.get('evidence_requirements',[]):
        c.execute('INSERT INTO rule_evidence_requirements(rule_version_id,evidence_key,description,requirement_type) VALUES (%s,%s,%s,%s)',(rid,requirement['key'],requirement['description'],requirement['type']))

    c.execute("DELETE FROM rule_relationships WHERE rule_version_id=%s AND relationship_type IN ('AND','OR')",(rid,))
    for dependency in d.get('dependencies',[]):
        related=c.execute("SELECT id FROM policy_rule_versions WHERE policy_version_id=%s AND clause_id=%s AND (definition->>'rule_sequence')::integer=%s AND id<>%s ORDER BY version DESC LIMIT 1",(row['policy_version_id'],dependency['clause_id'],dependency['rule_sequence'],rid)).fetchone()
        if related:
            c.execute('INSERT INTO rule_relationships(rule_version_id,related_rule_version_id,relationship_type,reason) VALUES (%s,%s,%s,%s)',(rid,related['id'],dependency['relationship'],'Reviewed compound requirement'))


def validate_source(c,payload):
    d=payload.definition
    source=c.execute('SELECT cl.*,pv.policy_id,pv.version,pv.is_current,pv.checksum,p.title,p.summary FROM policy_clauses cl JOIN policy_versions pv ON pv.id=cl.policy_version_id JOIN policy_documents p ON p.policy_id=pv.policy_id WHERE cl.id=%s FOR SHARE OF pv,p',(d.clause_id,)).fetchone()
    if not source or source['policy_id']!=payload.policy_id:
        raise HTTPException(422,'Select an ingested clause belonging to this policy')
    if not source['is_current']:
        raise HTTPException(409,'Source policy version changed; extract and review the current document')
    if d.source_excerpt not in source['source_excerpt']:
        raise HTTPException(422,'Source excerpt must be copied exactly from the selected clause')
    return source


def store_rule(payload: GovernedRuleInput,user,previous=None,extraction_key=None,c=None,force_draft=False):
    from .quantitative_rules import is_quantitative_rule
    if not is_quantitative_rule(payload.definition.model_dump()):
        raise HTTPException(422, 'Only quantitative rules with an explicit numeric threshold or bound are supported')
    if c is None:
        with shared_policy_connection() as connection:
            return store_rule(payload,user,previous,extraction_key,connection,force_draft)
    source=validate_source(c,payload)
    before=None; version=1; superseded=None
    if previous:
        reference=c.execute('SELECT rule_key FROM policy_rule_versions WHERE id=%s',(previous,)).fetchone()
        if reference:c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(reference['rule_key'],))
        before=c.execute('SELECT * FROM policy_rule_versions WHERE id=%s FOR UPDATE',(previous,)).fetchone()
        if not before or before['policy_id']!=payload.policy_id:
            raise HTTPException(404,'Rule not found')
        if before['created_by']!=user['user_id']: reviewer(user)
        key=before['rule_key'];entity_id=before['rule_entity_id']
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(key,))
        superseded=previous
        version=c.execute('SELECT COALESCE(MAX(version),0)+1 AS v FROM policy_rule_versions WHERE rule_key=%s',(key,)).fetchone()['v']
        if entity_id is None:
            entity=c.execute('INSERT INTO policy_rule_entities(policy_id,rule_code,rule_key) VALUES (%s,%s,%s) ON CONFLICT(rule_key) DO UPDATE SET rule_key=EXCLUDED.rule_key RETURNING id',(payload.policy_id,f'LEGACY-{before["id"]}',key)).fetchone();entity_id=entity['id']
    else:
        code=f'POL-{payload.policy_id}-C{source["sequence"]}-R{payload.definition.rule_sequence}'
        if extraction_key:
            code += '-Q'
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(code,))
        entity=c.execute('SELECT * FROM policy_rule_entities WHERE rule_code=%s',(code,)).fetchone()
        if entity:
            entity_id=entity['id'];key=entity['rule_key']
            version=c.execute('SELECT COALESCE(MAX(version),0)+1 AS v FROM policy_rule_versions WHERE rule_key=%s',(key,)).fetchone()['v']
            superseded=c.execute('SELECT id FROM policy_rule_versions WHERE rule_key=%s ORDER BY version DESC LIMIT 1',(key,)).fetchone()
            superseded=superseded['id'] if superseded else None
        else:
            key=str(uuid4())
            entity_id=c.execute('INSERT INTO policy_rule_entities(policy_id,rule_code,rule_key) VALUES (%s,%s,%s) RETURNING id',(payload.policy_id,code,key)).fetchone()['id']
    if extraction_key:
        existing=c.execute('SELECT * FROM policy_rule_versions WHERE extraction_key=%s',(extraction_key,)).fetchone()
        if existing:return dict(existing)
    definition=payload.definition.model_dump(mode='json')
    if before and str(before.get('extraction_key') or '').startswith('risk-knowledge:'):
        force_draft=True
        if extraction_key is None:
            extraction_key='risk-knowledge:revision:'+str(uuid4())
    extra_columns=',status,active' if force_draft else ''
    extra_values=",'Draft',false" if force_draft else ''
    row=c.execute(f"INSERT INTO policy_rule_versions(rule_key,version,policy_id,policy_version,policy_fingerprint,definition,effective_from,effective_to,created_by,rule_entity_id,policy_version_id,clause_id,superseded_version_id,extraction_key{extra_columns}) VALUES (%s,%s,%s,%s,md5(%s),%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s{extra_values}) RETURNING *",(key,version,payload.policy_id,source['version'],source['summary'],json.dumps(definition),payload.effective_from,payload.effective_to,user['user_id'],entity_id,source['policy_version_id'],source['id'],superseded,extraction_key)).fetchone()
    children(c,row);audit(c,before,row,user,'extract draft' if force_draft and not previous else 'extract rule' if extraction_key else 'create version',payload.definition.change_rationale)
    return dict(row)


def approval_ready(row,c=None):
    d=row['definition']
    # Business review may map inputs, but cannot supply a missing policy limit.
    import re
    numeric_values=[]
    for value in (d.get('threshold_value'),d.get('lower_bound'),d.get('upper_bound')):
        for item in value if isinstance(value,list) else [value]:
            if isinstance(item,(int,float)) and not isinstance(item,bool):numeric_values.append(item)
    if numeric_values:
        source=d.get('threshold_source')
        excerpt=d.get('source_excerpt') or ''
        tokens={float(token.replace(',','')) for token in re.findall(r'(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?',source or '')}
        if not source or source not in excerpt or any(float(value) not in tokens for value in numeric_values):
            raise HTTPException(409,'Numeric limits require exact policy source support; missing thresholds must remain unresolved')
    if row.get('extraction_key') and c is not None:
        document=c.execute('SELECT doc.extraction_status FROM policy_clauses cl JOIN inventory_documents doc ON doc.id=cl.document_id WHERE cl.id=%s',(row['clause_id'],)).fetchone()
        if not document or document['extraction_status']!='Completed':
            raise HTTPException(409,'Complete or retry source extraction before approving an AI-generated rule')
        if str(row['extraction_key']).startswith('risk-knowledge:'):
            from ..risk_knowledge.pipeline import fingerprint
            evidence=c.execute("SELECT payload FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=%s",('CPI-RULE-'+str(row['id']),)).fetchone()
            if not evidence or evidence['payload'].get('definition_fingerprint')!=fingerprint(d) or not evidence['payload'].get('validation',{}).get('source_provenance_verified'):
                raise HTTPException(409,'Submit this version through Risk Knowledge to refresh its source and mapping evidence')
    if row['policy_version_id'] is None or row['clause_id'] is None:
        raise HTTPException(409,'Legacy rule must be revised against an ingested source clause')
    if d.get('requirement_kind')=='guidance':
        raise HTTPException(409,'Guidance is not an operational requirement; reviewer must resolve its classification')
    logic=d.get('calculation_logic')
    manual=not logic or logic.get('method')=='manual'
    if not manual:
        if not d.get('operator'):raise HTTPException(409,'An executable rule needs an operator')
        if d['operator'] not in ('exists','does_not_exist') and d.get('threshold_value') is None and d['operator']!='between':
            raise HTTPException(409,'Complete the approved threshold or mark the check for manual review')
        if d['operator']=='between' and (d.get('lower_bound') is None or d.get('upper_bound') is None):
            raise HTTPException(409,'Complete both approved bounds')
        if not d.get('data_source'):raise HTTPException(409,'Confirm the input data source')
        if d.get('severity') is None:raise HTTPException(409,'Reviewer must assign operational severity')
    return True


def change_status(rule_id,action,comment,user):
    if action != 'comment':
        with shared_policy_connection() as c:
            target=c.execute("SELECT r.*,EXISTS(SELECT 1 FROM policy_rule_versions related WHERE related.rule_key=r.rule_key AND related.extraction_key LIKE 'risk-knowledge:%%') AS knowledge_family FROM policy_rule_versions r WHERE r.id=%s",(rule_id,)).fetchone()
        family_retirement=target and target.get('knowledge_family') is True and action in ('deactivate','retire')
        if not target or not str(target.get('extraction_key') or '').startswith('risk-knowledge:') and not family_retirement:
            raise HTTPException(410,'Legacy rules remain available by default; review actions apply to Risk Knowledge candidates')
        if action=='submit':
            if target['created_by']!=user['user_id']:
                reviewer(user)
            from ..risk_knowledge.pipeline import refresh_rule_evidence
            try:
                refresh_rule_evidence(dict(target),user,shared_policy_connection)
            except ValueError as error:
                raise HTTPException(422,str(error)) from None
            with shared_policy_connection() as c:
                refreshed=c.execute('SELECT * FROM policy_rule_versions WHERE id=%s',(rule_id,)).fetchone()
            if refreshed and refreshed['status']=='Approved' and refreshed.get('approved_by')=='system:auto-approval':
                return dict(refreshed)
    with shared_policy_connection() as c:
        # Lock by logical rule before its versions to serialize activation/version edits.
        reference=c.execute('SELECT rule_key FROM policy_rule_versions WHERE id=%s',(rule_id,)).fetchone()
        if not reference:raise HTTPException(404,'Rule not found')
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(reference['rule_key'],))
        before=c.execute('SELECT * FROM policy_rule_versions WHERE id=%s FOR UPDATE',(rule_id,)).fetchone()
        if action=='submit':
            if before['created_by']!=user['user_id']:reviewer(user)
        else:reviewer(user)
        transitions={'submit':({'Draft'},'Under Review'),'approve':({'Under Review'},'Approved'),'reject':({'Under Review'},'Rejected'),'activate':({'Approved','Inactive'},'Active'),'deactivate':({'Active'},'Inactive'),'retire':({'Draft','Under Review','Approved','Active','Inactive','Rejected'},'Retired')}
        if action!='comment':
            allowed,status=transitions[action]
            if before['status'] not in allowed:raise HTTPException(409,'Invalid rule lifecycle transition')
            if action in ('approve','activate'):
                approval_ready(before,c)
                source=c.execute('SELECT pv.is_current,pv.version,p.status AS policy_status,md5(p.summary) AS fingerprint FROM policy_versions pv JOIN policy_documents p ON p.policy_id=pv.policy_id WHERE pv.id=%s FOR SHARE OF pv,p',(before['policy_version_id'],)).fetchone()
                if not source or source['policy_status'].lower()!='active' or not source['is_current'] or source['version']!=before['policy_version'] or source['fingerprint']!=before['policy_fingerprint']:
                    raise HTTPException(409,'Underlying policy changed; review a new version')
            if action=='activate':
                if before['definition'].get('dependencies'):
                    dependencies=c.execute("SELECT COUNT(*) AS n FROM rule_relationships WHERE rule_version_id=%s AND relationship_type IN ('AND','OR')",(rule_id,)).fetchone()['n']
                    if dependencies!=len(before['definition']['dependencies']):
                        raise HTTPException(409,'Resolve all compound rule relationships before activation')
                overlap=c.execute("SELECT id FROM policy_rule_versions WHERE rule_key=%s AND status='Active' AND active AND id<>%s AND daterange(effective_from,effective_to,'[]') && daterange(%s::date,%s::date,'[]')",(before['rule_key'],rule_id,before['effective_from'],before['effective_to'])).fetchone()
                if overlap:raise HTTPException(409,'Deactivate the overlapping active version before activating this version')
            row=c.execute("UPDATE policy_rule_versions SET status=%s,active=%s,reviewed_by=%s,reviewed_at=CURRENT_TIMESTAMP,review_comments=%s,approval_decision=CASE WHEN %s IN ('approve','reject') THEN %s ELSE approval_decision END,approved_by=CASE WHEN %s='approve' THEN %s ELSE approved_by END,approval_date=CASE WHEN %s='approve' THEN CURRENT_TIMESTAMP ELSE approval_date END WHERE id=%s RETURNING *",(status,status=='Active',user['user_id'],comment,action,action,action,user['user_id'],action,rule_id)).fetchone()
        else:row=before
        c.execute('INSERT INTO rule_reviews(rule_version_id,reviewed_by,decision,comments) VALUES (%s,%s,%s,%s)',(rule_id,user['user_id'],action,comment))
        audit(c,before,row,user,action,comment)
        return dict(row)
