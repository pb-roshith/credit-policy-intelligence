"""Audit inventory, populate manufactured requests, and export DB-backed coverage.

python -m app.scripts.prepare_credit_data [--populate]
Existing canonical records are retained. Real/shared requests are never manufactured.
"""
import argparse
import json
import hashlib
import gzip
from collections import Counter
from datetime import date
from pathlib import Path
from ..database import initialize_database, shared_policy_connection, account_user_id, db_connection
from ..services.credit_data import sync_registry, synthetic_record, store_record, load_record, coverage_report
from ..services.rule_assessment import active_rule_candidates


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--populate', action='store_true'); parser.add_argument('--refresh-synthetic', action='store_true'); parser.add_argument('--registry-only',action='store_true'); args = parser.parse_args()
    initialize_database()
    rules = [r for r in active_rule_candidates(date.today()) if r['status']=='Active']
    attributes, mappings = sync_registry(rules)
    if args.registry_only:
        Path('../docs/credit-data-attribute-registry.json').write_text(json.dumps({'attributes':attributes,'mappings':mappings},default=str,indent=2),encoding='utf-8')
        summary_path=Path('../docs/credit-data-gap-analysis.json')
        if summary_path.exists():
            summary=json.loads(summary_path.read_text(encoding='utf-8'))
            summary.update(attributes=len(attributes),mapped_attributes=sum(a['metadata_status']=='MAPPED' for a in attributes),
                           metadata_gaps=sum(a['metadata_status']=='REQUIRES_DEFINITION' for a in attributes))
            summary_path.write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print(json.dumps({'attributes':len(attributes),'mappings':len(mappings)})); return
    with shared_policy_connection() as c:
        # This administrative command uses ownership only to select accounts. Every
        # subsequent read/write runs through the ordinary restricted account role.
        owners = c.execute('SELECT DISTINCT user_id FROM "user".credit_requests').fetchall()
    report = {'as_of_date': date.today().isoformat(), 'active_rules': len(rules), 'attributes': len(attributes),
              'mapped_attributes': sum(a['metadata_status']=='MAPPED' for a in attributes),
              'metadata_gaps': sum(a['metadata_status']=='REQUIRES_DEFINITION' for a in attributes),
              'calculation_methods': dict(Counter((r['definition'].get('calculation_logic') or {}).get('method') or 'undefined' for r in rules)),
              'populated_requests': 0, 'requests': []}
    scenarios = ['compliant', 'boundary', 'breach', 'multiple_breaches', 'missing', 'conflicting', 'warning', 'near_threshold']
    aggregate = {r['id']:set() for r in rules}
    for owner in owners:
        if not owner['user_id'] or owner['user_id']=='__legacy_unassigned__': continue
        token = account_user_id.set(owner['user_id'])
        try:
            with db_connection() as c:
                requests = c.execute('''SELECT cr.* FROM credit_requests cr JOIN credit_request_compliance cc
                    USING(user_id,credit_request_number) WHERE cr.shared_deal_id IS NULL
                    ORDER BY credit_request_number''').fetchall()
            for index, request in enumerate(requests):
                record = load_record(request['credit_request_number'])
                if record is None and args.populate:
                    store_record(synthetic_record(dict(request), rules, scenarios[index % len(scenarios)]))
                    report['populated_requests'] += 1; record = load_record(request['credit_request_number'])
                elif record and args.refresh_synthetic:
                    facts = [f for entities in record['entities'].values() for e in entities for f in e['attributes'].values()]
                    if all(f['provenance']['source_type']=='SYNTHETIC' for f in facts):
                        store_record(synthetic_record(dict(request),rules,scenarios[index % len(scenarios)]))
                        record=load_record(request['credit_request_number'])
                if record:
                    coverage = coverage_report(rules, record)
                    for row in coverage['rules']: aggregate[row['rule_id']].add(row['category'])
                    report['requests'].append({'account': owner['user_id'], 'request_id': record['request_id'], 'scenario': record.get('scenario'), 'revision':record['revision'], 'counts': coverage['counts']})
                    # Full rule-level detail for every request; counts come from the
                    # actual persisted record and current DB rule definitions.
                    destination = Path('../docs/credit-data-coverage') / hashlib.sha256(owner['user_id'].encode()).hexdigest()[:12]
                    destination.mkdir(parents=True, exist_ok=True)
                    with gzip.open(destination / (record['request_id']+'.json.gz'),'wt',encoding='utf-8') as output:
                        json.dump(coverage,output,default=str)
                    legacy_export = (destination / (record['request_id']+'.json')).resolve()
                    if legacy_export.parent == destination.resolve() and legacy_export.exists(): legacy_export.unlink()
        finally: account_user_id.reset(token)
    Path('../docs/credit-data-attribute-registry.json').write_text(json.dumps({'attributes':attributes,'mappings':mappings},default=str,indent=2),encoding='utf-8')
    precedence = ['fully_evaluable','manual_documentary','partially_supported','lacking_actual_data']
    report['stored_requests'] = len(report['requests'])
    report['aggregate_rule_coverage'] = dict(Counter(next((category for category in precedence if category in statuses),'lacking_actual_data') for statuses in aggregate.values()))
    report['aggregate_basis'] = 'Unique active DB rule versions; highest supported category across persisted demonstration requests'
    Path('../docs/credit-data-gap-analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='requests'},indent=2))


if __name__=='__main__': main()
