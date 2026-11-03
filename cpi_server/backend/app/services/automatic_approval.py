"""Automatic approval policy for persisted, source-backed extraction results."""
import hashlib
import json
import re
from types import SimpleNamespace
from .rule_governance import audit
from .source_quantities import restore_stated_amount_units

ACTOR='system:auto-approval'
REASON='Automatic approval requested for the policy extraction workflow'


def approve_knowledge(service):
    counts={}
    for table,key in (('taxonomy_concepts','concept_id'),('ontology_relationships','relationship_id')):
        allowed={c['concept_id'] for c in service.repo.all('taxonomy_concepts') if c['status']=='APPROVED'}
        updates=[]
        for item in service.repo.all(table):
            if item['status'] not in ('SOURCE','AI_PROPOSED','REVIEWED'):
                continue
            if table=='ontology_relationships' and (item['subject'] not in allowed or item['object'] not in allowed):
                continue
            updates.append((item[key],item|{'status':'APPROVED','review_notes':REASON}))
        if updates:
            service.repo.put_many(table,updates,{'actor':ACTOR,'reviewer':ACTOR,'action':'AUTO_APPROVE','notes':REASON})
        counts[table]=len(updates)
    return counts


def approve_rules(connection_factory,rule_ids=None):
    approved=[]
    with connection_factory() as c:
        rows=c.execute("""SELECT r.*,cl.source_excerpt AS original_excerpt
            FROM policy_rule_versions r JOIN policy_clauses cl ON cl.id=r.clause_id
            JOIN policy_versions pv ON pv.id=r.policy_version_id
            JOIN policy_documents p ON p.policy_id=r.policy_id
            WHERE r.extraction_key LIKE 'risk-knowledge:%%' AND r.status IN ('Draft','Under Review')
              AND pv.is_current AND p.version=r.policy_version AND md5(p.summary)=r.policy_fingerprint
              AND (%s::bigint[] IS NULL OR r.id=ANY(%s::bigint[]))
            ORDER BY r.id FOR UPDATE OF r""",(rule_ids,rule_ids)).fetchall()
        for raw in rows:
            before={k:v for k,v in raw.items() if k!='original_excerpt'}
            definition=dict(before['definition'])
            excerpt=definition.get('source_excerpt') or ''
            if not excerpt or excerpt not in raw['original_excerpt']:
                continue
            probe=SimpleNamespace(**{k:definition.get(k) for k in ('threshold_value','threshold_unit','lower_bound','upper_bound')})
            restore_stated_amount_units(probe,excerpt)
            source=definition.get('threshold_source') or ''
            numbers=[n for value in (probe.threshold_value,probe.lower_bound,probe.upper_bound)
                     for n in (value if isinstance(value,list) else [value]) if isinstance(n,(int,float)) and not isinstance(n,bool)]
            tokens={float(t.replace(',','')) for t in re.findall(r'(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?',source)}
            if not numbers or not source or source not in excerpt or any(float(n) not in tokens for n in numbers):
                continue
            definition.update(vars(probe))
            definition['missing_information']=[key for key in definition.get('missing_information',[]) if definition.get(key) is None]
            row=c.execute("""UPDATE policy_rule_versions SET definition=%s::jsonb,status='Approved',active=false,
                reviewed_by=%s,reviewed_at=CURRENT_TIMESTAMP,review_comments=%s,
                approved_by=%s,approval_date=CURRENT_TIMESTAMP,approval_decision='approve'
                WHERE id=%s RETURNING *""",(json.dumps(definition),ACTOR,REASON,ACTOR,before['id'])).fetchone()
            c.execute("INSERT INTO rule_reviews(rule_version_id,reviewed_by,decision,comments) VALUES (%s,%s,'approve',%s)",(row['id'],ACTOR,REASON))
            audit(c,before,row,{'user_id':ACTOR},'auto approve',REASON)
            checksum=hashlib.sha256(json.dumps(definition,sort_keys=True,default=str).encode()).hexdigest()
            c.execute("""UPDATE risk_knowledge_objects SET payload=payload||%s::jsonb
                WHERE kind='metadata' AND owner_id='' AND id=%s""",
                (json.dumps({'status':'APPROVED','definition_fingerprint':checksum,'approval_mode':'AUTOMATIC','approved_by':ACTOR}),
                 'CPI-RULE-'+str(row['id'])))
            approved.append(row['id'])
    return approved
