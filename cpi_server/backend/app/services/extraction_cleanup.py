"""Explicit, backed-up removal of superseded extraction generations."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from ..config import BACKUP_DIR


def remove_old_extracted_rules(connection_factory,backup_dir=None,old_rule_ids=None):
    backup_dir=Path(backup_dir or BACKUP_DIR).resolve()
    with connection_factory() as db:
        db.execute("SELECT pg_advisory_xact_lock(hashtext('rule-inventory-job'))")
        if db.execute("SELECT 1 FROM rule_inventory_jobs WHERE status IN ('Queued','Running')").fetchone():
            raise ValueError('Wait for the current extraction job before removing old rules')
        kept=db.execute("""SELECT r.id FROM policy_rule_versions r JOIN risk_knowledge_objects rk
            ON rk.kind='metadata' AND rk.owner_id='' AND rk.id='CPI-RULE-'||r.id::text
            WHERE r.extraction_key LIKE 'risk-knowledge:%%' AND r.status IN ('Approved','Active')
            AND EXISTS(SELECT 1 FROM jsonb_array_elements(rk.payload->'taxonomy_mappings') m WHERE m->>'status'='RESOLVED')""").fetchall()
        if not kept:
            raise ValueError('Enrich and approve the retained rules before removing old extractions')
        old=db.execute("""SELECT * FROM policy_rule_versions
            WHERE COALESCE(extraction_key,'') NOT LIKE 'risk-knowledge:%%'
              AND credit_data.is_quantitative_rule(definition)
              AND (%s::bigint[] IS NULL OR id=ANY(%s::bigint[])) ORDER BY id FOR UPDATE""",(old_rule_ids,old_rule_ids)).fetchall()
        ids=[row['id'] for row in old]
        if not ids:
            return {'removed':0,'backup':None}
        if db.execute('SELECT 1 FROM "user".request_rule_assessments WHERE rule_version_id=ANY(%s) LIMIT 1',(ids,)).fetchone():
            raise ValueError('Old rules have assessment history and must be archived rather than deleted')
        entities=sorted({row['rule_entity_id'] for row in old if row['rule_entity_id'] is not None})
        dependent={}
        columns={'rule_applicability_conditions':'rule_version_id','rule_input_requirements':'rule_version_id',
                 'rule_evidence_requirements':'rule_version_id','rule_reviews':'rule_version_id',
                 'rule_quality_reports':'rule_version_id','policy_rule_audit':'rule_id'}
        for table,column in columns.items():
            dependent[table]=db.execute(f'SELECT * FROM {table} WHERE {column}=ANY(%s)',(ids,)).fetchall()
        dependent['rule_relationships']=db.execute('SELECT * FROM rule_relationships WHERE rule_version_id=ANY(%s) OR related_rule_version_id=ANY(%s)',(ids,ids)).fetchall()
        checkpoints=db.execute("""SELECT * FROM rule_extraction_batches b WHERE EXISTS
            (SELECT 1 FROM jsonb_array_elements_text(b.rule_ids) item WHERE item.value::bigint=ANY(%s))""",(ids,)).fetchall()
        references=db.execute('SELECT id,superseded_version_id FROM policy_rule_versions WHERE superseded_version_id=ANY(%s) AND NOT(id=ANY(%s))',(ids,ids)).fetchall()
        metadata_ids=['CPI-RULE-'+str(identifier) for identifier in ids]
        snapshot={'format_version':1,'created_at':datetime.now(timezone.utc).isoformat(),
            'policy_rule_versions':old,'policy_rule_entities':db.execute('SELECT * FROM policy_rule_entities WHERE id=ANY(%s)',(entities,)).fetchall(),
            'dependent_tables':dependent,'rule_extraction_batches':checkpoints,'retained_supersession_references':references,
            'risk_knowledge_objects':db.execute("SELECT * FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=ANY(%s)",(metadata_ids,)).fetchall()}
        backup_dir.mkdir(parents=True,exist_ok=True)
        path=backup_dir/('old-extracted-rules-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]+'.json')
        payload=json.dumps(snapshot,default=str,ensure_ascii=False,indent=2).encode('utf-8')
        with path.open('xb') as output:
            output.write(payload)
        for table,column in columns.items():
            db.execute(f'DELETE FROM {table} WHERE {column}=ANY(%s)',(ids,))
        db.execute('DELETE FROM rule_relationships WHERE rule_version_id=ANY(%s) OR related_rule_version_id=ANY(%s)',(ids,ids))
        removed=set(ids)
        for checkpoint in checkpoints:
            remaining=[identifier for identifier in checkpoint['rule_ids'] if identifier not in removed]
            if remaining:
                db.execute('UPDATE rule_extraction_batches SET rule_ids=%s::jsonb WHERE id=%s',(json.dumps(remaining),checkpoint['id']))
            else:
                db.execute('DELETE FROM rule_extraction_batches WHERE id=%s',(checkpoint['id'],))
        db.execute('UPDATE policy_rule_versions SET superseded_version_id=NULL WHERE superseded_version_id=ANY(%s)',(ids,))
        db.execute('DELETE FROM policy_rule_versions WHERE id=ANY(%s)',(ids,))
        db.execute("DELETE FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=ANY(%s)",(metadata_ids,))
        db.execute('''DELETE FROM policy_rule_entities e WHERE e.id=ANY(%s)
            AND NOT EXISTS(SELECT 1 FROM policy_rule_versions r WHERE r.rule_entity_id=e.id)
            AND NOT EXISTS(SELECT 1 FROM "user".request_rule_assessments a WHERE a.rule_id=e.id)''',(entities,))
        db.execute("""INSERT INTO audit_events(entity_type,entity_id,new_value,action,actor,reason)
            VALUES ('PolicyRuleCleanup',%s,%s::jsonb,'remove old extractions','system:rule-cleanup',%s)""",
            (str(uuid4()),json.dumps({'removed_ids':ids,'backup':str(path),'sha256':hashlib.sha256(payload).hexdigest()}),
             'User requested removal of older extracted rules after enrichment of retained rules'))
        return {'removed':len(ids),'backup':str(path)}
