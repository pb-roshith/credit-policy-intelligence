"""Live AI demonstration of the user's illustrative LTV sentence, isolated from policy storage."""
import hashlib
import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import SEED_OUTPUTS_DIR
from app.risk_knowledge.repositories import SQLiteRepository
from app.risk_knowledge.semantic_pipeline import process_source,current_records
from app.risk_knowledge.semantic_extraction import assemble_graph
from app.risk_knowledge.semantic_model import validate_instance


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-exception',action='store_true')
    args=parser.parse_args()
    text='For salaried borrowers with home loans exceeding 50 lakhs, loan-to-value (LTV) shall not exceed 75 percent.'
    policy={'policy_id':999999,'title':'Illustrative user LTV example','source_type':'synthetic'}
    version={'id':999999,'version':'EXAMPLE','checksum':hashlib.sha256(text.encode()).hexdigest()}
    clauses=[{'id':999999,'sequence':1,'source_excerpt':text,'section_heading':'Illustrative eligibility example','page_number':1}]
    if args.with_exception:
        clauses.append({'id':1000000,'sequence':2,'source_excerpt':'Exceptions to the above LTV requirement require CR approval.','section_heading':'Exceptions','page_number':2})
        version['checksum']=hashlib.sha256('\n'.join(c['source_excerpt'] for c in clauses).encode()).hexdigest()
    with TemporaryDirectory() as temp:
        repo=SQLiteRepository(Path(temp)/'isolated-example.sqlite3')
        report=process_source(policy,version,clauses,repo,batcher=(lambda rows:[[c] for c in rows]) if args.with_exception else None)
        records=current_records(repo)
        graph=assemble_graph(records)
    graph['mode']='EXAMPLE'
    for node in graph['nodes']:
        if node['type']=='SourcePassage':node['properties']['origin']='ILLUSTRATIVE_EXAMPLE'
    result={'illustrative_only':True,'input':[c['source_excerpt'] for c in clauses],'report':report,'rules':records[0]['rules'],
        'context_history':records[0]['context_history'],'graph':graph,'validation':validate_instance(graph)}
    out=SEED_OUTPUTS_DIR/'extracted-knowledge'
    out.mkdir(parents=True,exist_ok=True)
    (out/('user-ltv-exception-cycle.json' if args.with_exception else 'user-ltv-example.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'report':report,'rules':[r['extracted'] for r in records[0]['rules']],'validation':result['validation']}),flush=True)


if __name__=='__main__':main()
