"""Run the authorized shared-policy extraction job and export its real results."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import shared_policy_connection
from app.routers.rules import enqueue_inventory
from app.services.rule_extraction import run_inventory_job
from app.risk_knowledge.repositories import PostgreSQLRepository
from app.risk_knowledge.semantic_pipeline import current_records
from app.risk_knowledge.semantic_extraction import assemble_graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--policies', nargs='*', type=int)
    parser.add_argument('--resume')
    args = parser.parse_args()
    user = {'user_id': 'system:semantic-extraction', 'role': 'admin'}
    if args.resume:
        with shared_policy_connection() as c:
            job = c.execute("UPDATE rule_inventory_jobs SET status='Queued' WHERE id=%s AND status IN ('Failed','Completed with errors') RETURNING *", (args.resume,)).fetchone()
        if not job: raise ValueError('Only failed/partial jobs can be resumed')
    else:
        with shared_policy_connection() as c:
            ids = args.policies or [p['policy_id'] for p in c.execute('SELECT policy_id FROM policy_documents ORDER BY policy_id').fetchall()]
        job = enqueue_inventory(user, ids)
    print(json.dumps({'job_id': str(job['id']), 'policy_ids': job['policy_ids']}), flush=True)
    run_inventory_job(str(job['id']), user)
    repo = PostgreSQLRepository(shared_policy_connection, None)
    records = current_records(repo)
    out = Path(__file__).resolve().parents[2] / 'outputs' / 'extracted-knowledge'
    out.mkdir(parents=True, exist_ok=True)
    with shared_policy_connection() as c:
        result = c.execute('SELECT * FROM rule_inventory_jobs WHERE id=%s', (job['id'],)).fetchone()
    for name, data in [('extraction-report.json', result), ('policy-rule-knowledge.json', records), ('knowledge-graph.json', assemble_graph(records))]:
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({'job_id': str(job['id']), 'status': result['status'], 'report': result['report'], 'output': str(out)}, default=str), flush=True)


if __name__ == '__main__': main()
