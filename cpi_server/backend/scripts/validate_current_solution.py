"""Read-only verification of the shared current policy projections; never calls AI."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database import shared_policy_connection
from app.risk_knowledge.semantic_model import validate_instance
from app.risk_knowledge.semantic_view import graph_view
from app.services.current_knowledge import inventory, policy_controls
from app.services.semantic_matching import load_matcher


def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'outputs'/'finalization'
    out.mkdir(parents=True,exist_ok=True)
    matcher=load_matcher()
    data=inventory(matcher)
    published={r['id'] for r in data['rules'] if r['published_in_graph']}
    graph_rules={n['id'] for n in matcher.graph['nodes'] if n['type']=='PolicyRule'}
    controls=policy_controls(matcher=matcher)
    checks={
        'current_policy_sources_equal_processed_policy_set':
            {d['policy_id'] for d in matcher.documents}=={r['policy_id'] for r in matcher.records},
        'published_library_rules_equal_graph_rules':published==graph_rules,
        'controls_equal_published_qualitative_rules':
            {c['control_id'] for c in controls}=={r['id'] for r in data['rules'] if r['published_in_graph'] and r['rule_category']=='QUALITATIVE'},
        'no_proposed_rules_in_graph':not ({r['id'] for r in data['rules'] if r['status']=='PROPOSED'} & graph_rules),
        'all_published_rules_have_source_edges':published<={e['subject'] for e in matcher.graph['relationships'] if e['predicate']=='DERIVED_FROM'},
        'semantic_schema_conforms':validate_instance(matcher.graph)['conforms'],
    }
    for record in matcher.records:
        view=graph_view(matcher.records,policy_id=record['policy_id'])
        checks['policy_'+str(record['policy_id'])+'_expands_to_rules']=any(e['predicate']=='CONTAINS_RULE' for e in view['edges'])
    # Runtime report endpoints use the same fingerprint to exclude earlier assessments.
    with shared_policy_connection() as db:
        release=db.execute("SELECT activated_at FROM solution_releases WHERE release_key='semantic-finalization-v1'").fetchone()
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'release':'semantic-finalization-v1',
        'release_activated_at':release['activated_at'].isoformat(),
        'pipeline':data['pipeline'],'ontology_version':data['ontology_version'],
        'knowledge_fingerprint':matcher.fingerprint,'counts':data['summary'],
        'review_queue':{'policy_scopes':sum((r.get('policy_scope') or {}).get('status')!='APPROVED' for r in matcher.records),
            'proposed_rules':data['summary']['proposed_rules'],
            'unresolved_passages':sum(c['disposition']=='UNRESOLVED' for r in matcher.records for c in r['coverage'])},
        'checks':checks,'passed':all(checks.values()),
        'scope':'Current shared source corpus only; no account identities or credit request facts exported.'}
    (out/'consistency-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    files=['outputs/extracted-knowledge/connected-policy-knowledge.zip',
        'outputs/ontology/credit-policy-ontology-v1.2.0.zip','outputs/policy-taxonomy/policy-taxonomy.json',
        'outputs/policy-taxonomy/policy-taxonomy.xlsx','outputs/finalization/consistency-report.json']
    if (out/'http-smoke.json').exists():files.append('outputs/finalization/http-smoke.json')
    manifest={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
    (out/'manifest.json').write_text(json.dumps({'knowledge_fingerprint':matcher.fingerprint,'sha256':manifest},indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':len(checks),'counts':report['counts'],'review_queue':report['review_queue']}))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
