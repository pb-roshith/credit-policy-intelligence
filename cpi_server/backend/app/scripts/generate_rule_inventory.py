"""Generate drafts from registered active policy files; never approve rules."""
import argparse
import json
import logging
from pathlib import Path
from ..config import ADMIN_USER_ID
from ..routers.rules import enqueue_inventory
from ..services.rule_extraction import run_inventory_job
from ..database import shared_policy_connection


def main():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    parser=argparse.ArgumentParser()
    parser.add_argument('--policy-id',type=int,action='append')
    parser.add_argument('--report',type=Path,default=Path('inventory-extraction-report.json'))
    args=parser.parse_args()
    user={'user_id':ADMIN_USER_ID,'role':'admin'}
    job=enqueue_inventory(user,args.policy_id)
    print('Inventory job:',job['id'],'Policies:',len(job['policy_ids']),flush=True)
    run_inventory_job(str(job['id']),user)
    from ..services.inventory_operations import finalize_inventory_summary
    finalize_inventory_summary(str(job['id']))
    with shared_policy_connection() as c:
        result=c.execute('SELECT * FROM rule_inventory_jobs WHERE id=%s',(job['id'],)).fetchone()
    args.report.write_text(json.dumps(result,default=str,indent=2),encoding='utf-8')
    from ..services.inventory_operations import exception_report
    exceptions=args.report.with_name(args.report.stem+'-exceptions.json')
    exceptions.write_text(json.dumps(exception_report(str(job['id'])),default=str,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'report':result['report'],'exception_report':str(exceptions)},default=str),flush=True)

if __name__=='__main__':main()
