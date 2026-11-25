"""Verify the archived sources, competency paths and rebuilt graph against the shared catalog."""
import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import SEED_OUTPUTS_DIR
from app.database import shared_policy_connection
from app.risk_knowledge.competency_queries import answer
from app.routers.risk_knowledge import effective_rule_edition
from app.services.policy_graph_rebuild import rebuild_summary, store_snapshot
from app.services.policy_ingestion import parse_document
from app.services.semantic_matching import load_matcher


def verify(matcher):
    archived = {path.stem: path for path in (BASE_DIR / 'inventory_sources').iterdir() if path.is_file()}
    verified = []
    for record in matcher.records:
        checksum = record['source_checksum']
        path = archived.get(checksum)
        if path is None or sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Unverified archive for policy {record['policy_id']}")
        passages = parse_document(path)
        if [p['source_excerpt'] for p in passages] != [p['source_excerpt'] for p in record['source_clauses']]:
            raise ValueError(f"Archive passage differences for policy {record['policy_id']}")
        verified.append({'policy_id': record['policy_id'], 'title': record['policy_name'],
                         'version': record['policy_version'], 'checksum': checksum, 'passages': len(passages)})

    scenarios = [
        ('borrower', '', {'credit_request_number': 'ILLUSTRATIVE', 'facility': 'CRE loans'}),
        ('industry', 'Hospitality', None), ('industry', 'Commercial Real Estate', None),
        ('industry', 'Tier 1', None), ('geography', 'India', None),
        ('geography', 'foreign jurisdiction', None), ('product', 'CRE loans', None),
        ('product', 'Construction Loan', None), ('rating', '', None), ('exposure', '', None),
        ('collateral', '', None), ('breach_approval', '', None), ('exceptions', '', None),
    ]
    results = []
    for question, value, proposal in scenarios:
        result = answer(matcher, question, value, request=proposal, limit=3)
        results.append({'question': question, 'value': value, 'illustrative_request': proposal is not None,
                        'total': result['total'], 'examples': result['results']})
    classified = next((edge['subject'] for edge in matcher.graph['relationships'] if edge['predicate'] == 'CLASSIFIED_AS'), None)
    if classified:
        results.append(answer(matcher, 'policy_class', classified))
    date_check = effective_rule_edition(15, date(2026, 10, 1), '', 0, 2) if any(r['policy_id'] == 15 for r in matcher.records) else None
    return {'model': rebuild_summary(matcher), 'archived_sources': verified,
            'missing_extraction_policies': sorted({d['policy_id'] for d in matcher.documents} - {r['policy_id'] for r in matcher.records}),
            'relationship_counts': dict(Counter(edge['predicate'] for edge in matcher.graph['relationships'])),
            'competency_checks': results, 'effective_date_check': date_check,
            'coverage': answer(matcher, 'coverage')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', action='store_true', help='Persist the validated graph in the shared policy store.')
    args = parser.parse_args()
    matcher = load_matcher()
    result = verify(matcher)
    if args.store:
        with shared_policy_connection() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('rule-inventory-job'))")
            if connection.execute("SELECT 1 FROM rule_inventory_jobs WHERE status IN ('Queued','Running')").fetchone():
                raise ValueError('An extraction is running')
            current = load_matcher()
            if matcher.fingerprint != current.fingerprint:
                raise ValueError('The policy sources changed during verification. Run it again.')
            store_snapshot(connection, current, result['model'])
    path = SEED_OUTPUTS_DIR / 'extracted-knowledge' / 'competency-report.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({'report': str(path), 'stored': args.store, **result['model']}))


if __name__ == '__main__':
    main()
