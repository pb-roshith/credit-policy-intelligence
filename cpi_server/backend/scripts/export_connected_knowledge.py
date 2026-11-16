"""Export the current real source-backed graph and a business review workbook."""
import json
import hashlib
from zipfile import ZipFile,ZIP_DEFLATED
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database import shared_policy_connection
from app.risk_knowledge.repositories import PostgreSQLRepository
from app.risk_knowledge.semantic_pipeline import current_records
from app.risk_knowledge.semantic_extraction import assemble_graph,approved_rules
from app.risk_knowledge.semantic_model import validate_instance,semantic_contract,instance_schema
from app.risk_knowledge.semantic_rdf import instance_graph,ontology_graph,shapes_graph
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.utils import get_column_letter


def main():
    records=current_records(PostgreSQLRepository(shared_policy_connection,None))
    graph=assemble_graph(records)
    validation=validate_instance(graph)
    if not validation['conforms']:raise ValueError(validation['errors'][:3])
    active=approved_rules(records)
    out=Path(__file__).resolve().parents[2]/'outputs'/'extracted-knowledge'
    out.mkdir(parents=True,exist_ok=True)
    summary={'policies':len(records),'source_passages':sum(len(r['source_clauses']) for r in records),
        'extracted_rules':sum(len(r['rules']) for r in records),'published_rules':len(active),
        'proposed_rules':sum(s['status']=='PROPOSED' for r in records for s in r['rules']),
        'approved_policy_scopes':sum((r.get('policy_scope') or {}).get('status')=='APPROVED' for r in records),
        'policy_scopes_needing_review':sum((r.get('policy_scope') or {}).get('status')!='APPROVED' for r in records),
        'unresolved_passages':sum(s['disposition']=='UNRESOLVED' for r in records for s in r['coverage']),
        'failed_batches':sum(len(r['failed_batches']) for r in records),
        'batches_using_existing_graph':sum(bool(h['graph_rule_ids']) for r in records for h in r['context_history']),
        'resolved_exception_nodes':sum(n['type']=='Exception' for n in graph['nodes']),
        'nodes':len(graph['nodes']),'relationships':len(graph['relationships']),
        'ontology_version':graph['ontology_version'],'validation':validation}
    for name,data in [('knowledge-graph.json',graph),('policy-rule-knowledge.json',records),('knowledge-validation.json',summary)]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    instance_graph(graph).serialize(out/'knowledge-graph.ttl',format='turtle')
    book=Workbook();book.remove(book.active)
    def sheet(name,columns,rows):
        ws=book.create_sheet(name);ws.append(columns)
        for row in rows:
            ws.append([json.dumps(row.get(k),ensure_ascii=False) if isinstance(row.get(k),(dict,list)) else row.get(k) for k in columns])
        for c in ws[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='173B50')
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value,str):c.data_type='s'
                c.alignment=Alignment(wrap_text=True,vertical='top')
        for i,key in enumerate(columns,1):ws.column_dimensions[get_column_letter(i)].width=80 if key in ('source_quote','conditions','validation_error','reason') else 28
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    rows=[]
    for record in records:
        sources={c['id']:c for c in record['source_clauses']}
        for r in record['rules']:
            d=r['extracted'];source=sources[d['clause_id']]
            rows.append({**d,'rule_id':r['id'],'policy':record['policy_name'],'policy_version':record['policy_version'],
                'status':r['status'],'published_in_graph':r['id'] in active,'validation_error':r['validation_error'],
                'approved_by':r['approved_by'],'page':source.get('page_number'),'section':source.get('section_heading'),
                'source_checksum':record['source_checksum'],'synthetic':record['synthetic']})
    columns=['rule_id','policy','policy_version','name','status','published_in_graph','rule_kind','products','customer_segments','geographies',
        'metrics','thresholds','conditions','base_rule_ref','approvals','evidence_requirements','taxonomy_ids',
        'page','section','approved_by','validation_error','source_checksum','synthetic','source_quote']
    sheet('Rules',columns,rows)
    sheet('Policy scopes',['policy','policy_version','status','conditions','exclusions','unrestricted','validation_error','sources','approved_by'],
          [{'policy':r['policy_name'],'policy_version':r['policy_version'],**(r.get('policy_scope') or {})} for r in records])
    sheet('Review queue',columns,[r for r in rows if r['status']!='APPROVED' or not r['published_in_graph']])
    sheet('Coverage',['policy','clause_id','disposition','reason'],[{'policy':r['policy_name'],**c} for r in records for c in r['coverage']])
    sheet('Batch failures',['policy','clause_ids','error'],[{'policy':r['policy_name'],**c} for r in records for c in r['failed_batches']])
    sheet('Graph context history',['policy','batch','graph_rule_ids','graph_context_digest','ontology_version','taxonomy_digest'],[{'policy':r['policy_name'],**c} for r in records for c in r['context_history']])
    sheet('Summary',['item','value'],[{'item':k,'value':v} for k,v in summary.items()])
    book.save(out/'extracted-policy-rules.xlsx')
    lines=['# Extracted policy rules and knowledge graph','',
        'These files contain actual AI extraction results from the registered policy corpus. Synthetic source labels are retained.','',
        '[Review workbook](extracted-policy-rules.xlsx) · [Machine-readable graph](knowledge-graph.json) · [RDF graph](knowledge-graph.ttl) · [Validation](knowledge-validation.json)','',
        *[f'- {k}: {v}' for k,v in summary.items() if k!='validation'],'',
        'Validated rules receive auditable automatic initial approval. Proposed rules, ambiguous references and failed batches remain visible in the review queue. Human corrections/rejections are versioned in the audit history and survive extraction retries.','',
        'The graph supplies bounded, source-backed context to subsequent AI batches. Context IDs and fingerprints are recorded in the workbook. Context cannot invent a threshold or policy scope.','',
        'In the application use Policy Rule Library for review and Knowledge graph for progressive exploration. Clicking a node opens its connected neighborhood, with six neighbors drawn at a time and a searchable directory for all policies and rules.','',
        'Policy versions can carry source-backed HAS_APPLICABILITY and HAS_EXCLUSION condition groups. Compliance Review inherits this scope before checking individual rule conditions. Proposed scopes remain unresolved and can be reviewed in Policy Evidence.','',
        'Only current source-backed corpus artifacts are included in the release package.','']
    (out/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    profile=out/'ontology';profile.mkdir(exist_ok=True)
    for name,data in [('semantic-model.json',semantic_contract()),('instances.schema.json',instance_schema())]:
        (profile/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    ontology_graph().serialize(profile/'ontology.ttl',format='turtle')
    shapes_graph().serialize(profile/'shapes.ttl',format='turtle')
    names=['README.md','knowledge-graph.json','knowledge-graph.ttl','policy-rule-knowledge.json',
        'knowledge-validation.json','extracted-policy-rules.xlsx','ontology/semantic-model.json',
        'ontology/instances.schema.json','ontology/ontology.ttl','ontology/shapes.ttl']

    manifest={'ontology_version':graph['ontology_version'],'files':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in names}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    with ZipFile(out/'connected-policy-knowledge.zip','w',ZIP_DEFLATED) as package:
        for name in [*names,'manifest.json']:package.write(out/name,name)
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
