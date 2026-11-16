"""Populate missing current policy-wide graph scopes; existing rules are preserved."""
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database import shared_policy_connection
from app.risk_knowledge.repositories import PostgreSQLRepository
from app.risk_knowledge.semantic_pipeline import current_records
from app.risk_knowledge.semantic_scope import enrich_scope


if __name__=='__main__':
    repo=PostgreSQLRepository(shared_policy_connection,None)
    records=current_records(repo)
    def work(record):
        result=enrich_scope(repo,record)
        scope=result.get('policy_scope',{})
        return record['policy_id'],scope.get('status','MISSING'),scope.get('validation_error')
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(work,r) for r in records]
        for future in as_completed(futures):
            try:print(future.result(),flush=True)
            except Exception as error:print('FAILED',type(error).__name__,str(error)[:240],flush=True)
