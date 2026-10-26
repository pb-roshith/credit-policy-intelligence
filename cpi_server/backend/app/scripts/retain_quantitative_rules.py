"""Back up and retire nonnumeric requirements, preserving assessment history."""
import json
from datetime import datetime
from pathlib import Path
from ..database import shared_policy_connection
from ..services.quantitative_rules import is_quantitative_rule


def main():
    with shared_policy_connection() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('rule-inventory-job'))")
        if c.execute("SELECT 1 FROM rule_inventory_jobs WHERE status IN ('Queued','Running')").fetchone():
            raise RuntimeError('Wait for the active inventory job before cleanup')
        c.execute('LOCK TABLE policy_rule_versions IN EXCLUSIVE MODE')
        rows=c.execute('SELECT * FROM policy_rule_versions ORDER BY id').fetchall()
        removed=[r['id'] for r in rows if not is_quantitative_rule(r['definition'])
                 and (r['active'] or r['status'] != 'Retired')]
        if not removed:
            print(json.dumps({'removed':0,'remaining':sum(is_quantitative_rule(r['definition']) for r in rows)}));return
        tables=('policy_rule_versions','policy_rule_entities','policy_rule_audit','audit_events',
                'rule_applicability_conditions','rule_input_requirements','rule_evidence_requirements',
                'rule_relationships','rule_reviews','rule_quality_reports','rule_extraction_batches',
                'policy_extraction_reports','rule_inventory_jobs')
        backup={table:c.execute('SELECT * FROM '+table).fetchall() for table in tables}
        path=Path('quantitative-inventory-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
        path.write_text(json.dumps(backup,default=str,indent=2),encoding='utf-8')
        migration=Path(__file__).resolve().parents[1]/'migrations'/'005_quantitative_inventory.sql'
        c.execute(migration.read_text(encoding='utf-8'))
        # Old checkpoints contain removed IDs and cannot represent the new extraction scope.
        c.execute('DELETE FROM rule_extraction_batches')
        c.execute("UPDATE inventory_documents SET extraction_status='Pending',error=NULL")
        c.execute("INSERT INTO audit_events(entity_type,entity_id,new_value,action,actor,reason) VALUES ('RuleInventory','quantitative-only',%s::jsonb,'Remove nonnumeric requirements','admin','User requested quantitative rules only')",(json.dumps({'removed_rule_ids':removed,'backup':str(path)}),))
        remaining=c.execute('SELECT COUNT(*) AS n FROM policy_rule_versions WHERE credit_data.is_quantitative_rule(definition)').fetchone()['n']
    print(json.dumps({'removed':len(removed),'remaining':remaining,'backup':str(path)}))


if __name__=='__main__':main()
