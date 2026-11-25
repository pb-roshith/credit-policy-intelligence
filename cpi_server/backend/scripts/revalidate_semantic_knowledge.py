"""Recheck existing AI outputs against exact source text; no model calls."""
import json
import argparse
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import SEED_OUTPUTS_DIR
from app.database import shared_policy_connection
from app.risk_knowledge.repositories import PostgreSQLRepository
from app.risk_knowledge.semantic_pipeline import current_records, save, resolve_record_references
from app.risk_knowledge.semantic_extraction import (ACTOR, ExtractedRule, restore_source_wrapping,
    validate_rule, taxonomy_context, assemble_graph, approved_rules, sources_in_batches, digest, PIPELINE_VERSION,normative_clause)
from app.risk_knowledge.semantic_model import VERSION
from app.risk_knowledge.semantic_model import validate_instance
from app.risk_knowledge.policy_taxonomy import structural_reason,heading_for


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--completed-only',action='store_true')
    parser.add_argument('--restore-checkpoint',type=Path)
    args=parser.parse_args()
    repo=PostgreSQLRepository(shared_policy_connection,None)
    records=current_records(repo)
    expected_digests={r['id']:r['content_digest'] for r in records}
    if args.restore_checkpoint:
        checkpoints={r['id']:r for r in json.loads(args.restore_checkpoint.read_text(encoding='utf-8'))}
        for record in records:
            previous=checkpoints.get(record['id'])
            if not previous or previous['policy_version_id']!=record['policy_version_id'] or previous['source_checksum']!=record['source_checksum']:continue
            ids={r['id'] for r in record['rules']}
            record['rules'] += [r for r in previous['rules'] if r['id'] not in ids and r['status']=='APPROVED']
    active=set()
    if args.completed_only:
        with shared_policy_connection() as c:
            jobs=c.execute("SELECT progress FROM rule_inventory_jobs WHERE status IN ('Running','Queued')").fetchall()
        active={p['policy_id'] for job in jobs for p in job['progress'] if p['status']=='Running'}
    for record in records:
        if record['policy_id'] in active:continue
        expected=record['content_digest']
        sources={c['id']:c for c in record['source_clauses']}
        supplied_candidates={i for h in record['context_history'] for i in h['graph_rule_ids']}
        revised=[]
        for row in record['rules']:
            if row.get('human_override'):
                revised.append(row); continue
            if re.search(r'(?i)\bnon[- ]rule\b|^no rule',row['extracted']['name']): continue
            primary=sources[row['extracted']['clause_id']]
            if structural_reason(primary['source_excerpt'],heading_for(primary)):continue
            rule=ExtractedRule.model_validate(row['extracted'])
            restore_source_wrapping(rule,sources,sources)
            error=validate_rule(rule,sources,sources,supplied_candidates,{t['id'] for t in taxonomy_context()})
            row.update(extracted=rule.model_dump(mode='json'),status='PROPOSED' if error else 'APPROVED',
                validation_error=error,approved_by=None if error else ACTOR,approval_mode=None if error else 'AUTOMATIC')
            revised.append(row)
        record['rules']=revised
        resolve_record_references(record,[r for r in records if r['id']!=record['id']])
        supported_ids={s['clause_id'] for r in revised if r['status']=='APPROVED' for s in r['extracted']['supporting_sources']}
        for c in record['coverage']:
            rows=[r for r in revised if r['extracted']['clause_id']==c['clause_id']]
            source=sources[c['clause_id']]
            if not rows and (c.get('ai_disposition')=='NON_RULE' or structural_reason(source['source_excerpt'],heading_for(source)) or c['reason']=='AI returned rules for a non-rule passage'):
                c.update(disposition='NON_RULE',reason='Source structure or non-rule content retained')
            if not rows and c['clause_id'] not in supported_ids and normative_clause(source):
                c.update(disposition='UNRESOLVED',reason='Normative source passage has no extracted requirement or supporting-source link')
            if rows and all(r['status']=='APPROVED' for r in rows) and c.get('ai_disposition','RULES')=='RULES':
                c.update(disposition='RULES',reason='Source evidence and semantic constraints revalidated')
            elif rows and any(r['status']=='PROPOSED' for r in rows):
                c.update(disposition='UNRESOLVED',reason='; '.join(sorted({r['validation_error'] for r in rows if r['validation_error']})))
        if not revised:
            for c in record['coverage']:
                source=sources[c['clause_id']]
                if re.search(r'\bshall\b|\bmust\b|is required|required to',source['source_excerpt'],re.I) and not re.search(r'training|scenario|suggested.*prompt',source.get('section_heading') or '',re.I):
                    c.update(disposition='UNRESOLVED',reason='Normative source language has no extracted requirement')
        for batch in sources_in_batches([c for c in record['source_clauses'] if not structural_reason(c['source_excerpt'],heading_for(c))]):
            ids={c['id'] for c in batch}
            key=digest([VERSION,PIPELINE_VERSION,[(c['id'],c['source_excerpt']) for c in batch]])
            rows=[r for r in record['rules'] if r['extracted']['clause_id'] in ids]
            coverage=[c for c in record['coverage'] if c['clause_id'] in ids]
            if len(coverage)==len(ids) and all(c['disposition']!='UNRESOLVED' for c in coverage) and all(r['status']!='PROPOSED' for r in rows):
                if key not in record['completed_batches']:record['completed_batches'].append(key)
            else:record['completed_batches']=[k for k in record['completed_batches'] if k!=key]
    graph=assemble_graph(records)
    report=validate_instance(graph)
    if not report['conforms']:raise ValueError(report['errors'][:3])
    for record in records:
        if record['policy_id'] not in active:save(repo,record,expected_digests[record['id']],ACTOR,'REVALIDATE_EXACT_SOURCE')
    out=SEED_OUTPUTS_DIR/'extracted-knowledge'
    out.mkdir(parents=True,exist_ok=True)
    summary={'policies':len(records),'extracted_rules':sum(len(r['rules']) for r in records),
        'published_rules':len(approved_rules(records)),'proposed_rules':sum(x['status']=='PROPOSED' for r in records for x in r['rules']),
        'nodes':len(graph['nodes']),'relationships':len(graph['relationships']),
        'validation':validate_instance(graph)}
    for name,data in [('policy-rule-knowledge.json',records),('knowledge-graph.json',graph),('knowledge-validation.json',summary)]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
