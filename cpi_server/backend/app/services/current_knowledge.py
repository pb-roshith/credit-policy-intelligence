"""Shared current semantic projections for policy screens and reporting."""
from collections import defaultdict
from ..risk_knowledge.semantic_view import rule_inventory
from .semantic_matching import load_matcher
from .semantic_assessment import ENGINE_VERSION


def create_current_views(connection):
    connection.execute('ALTER TABLE "user".dashboard_insights ADD COLUMN IF NOT EXISTS knowledge_fingerprint TEXT')
    connection.execute('''CREATE OR REPLACE VIEW "user".current_policy_exceptions WITH (security_invoker=true) AS
        SELECT * FROM "user".credit_request_exceptions
        WHERE rationale->'knowledge_context'->>'knowledge_fingerprint' = NULLIF(current_setting('app.knowledge_fingerprint',true),'')
           OR (rationale->>'data_origin'='DATA_MANUFACTURING' AND rationale->>'synthetic'='true')''')
    connection.execute('GRANT SELECT ON "user".current_policy_exceptions TO credit_user_runtime')
    connection.execute("CREATE TABLE IF NOT EXISTS credit_data.solution_releases (release_key TEXT PRIMARY KEY,activated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    connection.execute("INSERT INTO credit_data.solution_releases(release_key) VALUES ('semantic-finalization-v1') ON CONFLICT DO NOTHING")
    cutoff=connection.execute("SELECT activated_at FROM credit_data.solution_releases WHERE release_key='semantic-finalization-v1'").fetchone()['activated_at']
    from psycopg import sql
    connection.execute(sql.SQL("""CREATE OR REPLACE VIEW "user".current_ai_observability_spans WITH (security_invoker=true) AS
        SELECT * FROM "user".ai_observability_spans WHERE operation IN
        ('semantic_policy_extraction','semantic_policy_scope','graph_rag_explanation','semantic_policy_copilot')
        OR (started_at>={} AND operation IN ('portfolio_insights','compliance_copilot','exception_rationale',
          'scenario_recommendations','portfolio_copilot','policy_generation','policy_summary'))""").format(sql.Literal(cutoff)))
    connection.execute('GRANT SELECT ON "user".current_ai_observability_spans TO credit_user_runtime')



def bind_current_views(connection,fingerprint):
    connection.execute("SELECT set_config('app.knowledge_fingerprint',%s,true)",(fingerprint,))


def current_review(review,fingerprint=None):
    return (review.get('assessment_scope')=='current-semantic-graph' and review.get('engine_version')==ENGINE_VERSION
            and (fingerprint is None or review.get('knowledge_fingerprint')==fingerprint))


def current_reviews(rows,fingerprint):
    return [r for r in rows if current_review(r.get('review') or {},fingerprint)]


def inventory(matcher=None):
    matcher=matcher or load_matcher()
    result=rule_inventory(matcher.records)
    result['knowledge_fingerprint']=matcher.fingerprint
    result['pipeline']='policy-semantic-llm-v1'
    result['ontology_version']=matcher.graph['ontology_version']
    result['summary']={'policies':len(matcher.documents),'processed_policies':len(matcher.records),
        'source_passages':len(matcher.clauses),'extracted_rules':len(result['rules']),
        'published_rules':sum(r['published_in_graph'] for r in result['rules']),
        'proposed_rules':sum(r['status']=='PROPOSED' for r in result['rules']),
        'qualitative_rules':sum(r['rule_category']=='QUALITATIVE' for r in result['rules']),
        'quantitative_rules':sum(r['rule_category']=='QUANTITATIVE' for r in result['rules']),
        'graph_nodes':len(matcher.graph['nodes']),'graph_relationships':len(matcher.graph['relationships'])}
    return result


def policy_controls(policy_id=None,matcher=None):
    matcher=matcher or load_matcher();data=inventory(matcher)
    result=[]
    for r in data['rules']:
        if not r['published_in_graph'] or r['rule_category']!='QUALITATIVE' or (policy_id is not None and r['policy_id']!=policy_id):continue
        d=r['extracted']
        result.append({'control_id':r['id'],'policy_id':r['policy_id'],'policy_name':r['policy_name'],
            'control_name':d['name'],'control_description':d['source_quote'],'control_owner':', '.join(a['name'] for a in d['approvals']) or None,
            'clause_number':r['source'].get('clause_number') or str(d['clause_id']),'control_type':'Approval requirement' if d['approvals'] else 'Qualitative requirement',
            'status':r['status'],'source_page':r['source'].get('page_number'),'published_in_graph':True,
            'knowledge_fingerprint':matcher.fingerprint})
    return result


def policy_relationships(policy_id,matcher=None):
    """Find related documents by explicit catalogue family and source-backed concepts.

    Graph entity IDs can be scoped to a policy version. Compare their typed
    business values, not their storage IDs. These are discovery relationships,
    never additional applicability constraints or inferred policy requirements.
    """
    from .semantic_matching import normalized
    from ..database import shared_policy_connection
    matcher=matcher or load_matcher()
    with shared_policy_connection() as db:
        docs={d['policy_id']:dict(d) for d in db.execute('SELECT policy_id,library_policy_id,title,parent_policy FROM policy_documents').fetchall()}
    if policy_id not in docs:return []
    nodes={n['id']:n for n in matcher.graph['nodes']}
    owners={rid:record['policy_id'] for rid,(record,row) in matcher.rows.items()}
    terms=defaultdict(set);labels={}
    fields={'APPLIES_TO_PRODUCT':('Product','product_code','product','products'),
            'APPLIES_TO_SEGMENT':('CustomerSegment','segment_code','customer_segment','customer segments'),
            'USES_METRIC':('RiskMetric','metric_key',None,'metrics')}
    for edge in matcher.graph['relationships']:
        owner=owners.get(edge['subject']);node=nodes.get(edge['object'])
        if owner is None or node is None:continue
        if edge['predicate'] in fields:
            kind,prop,facet,category=fields[edge['predicate']]
            if node['type']!=kind:continue
            value=node['properties'].get(prop) or node['label']
            key=(category,normalized(str(value).replace('_',' '),facet))
            if not key[1]:continue
            labels.setdefault(key,node['label'])
        elif edge['predicate']=='CLASSIFIED_AS' and node['type']=='TaxonomyConcept':
            value=node['properties'].get('taxonomy_id','')
            # General categories such as eligibility/approval do not make every
            # credit document related. Specific observed topics provide context.
            if not value.startswith('PTX-TOPIC-'):continue
            key=('topics',value)
            labels.setdefault(key,value.removeprefix('PTX-TOPIC-').replace('-',' '))
        else:continue
        terms[key].add(owner)
    shared=defaultdict(lambda:defaultdict(set))
    for key,policies in terms.items():
        if policy_id in policies:
            for other in policies-{policy_id}:
                if other in docs:shared[other][key[0]].add(labels[key])
    parent=str(docs[policy_id].get('parent_policy') or '').strip()
    if parent and normalized(parent) not in ('unknown','n/a','none'):
        for other,doc in docs.items():
            if other!=policy_id and normalized(doc.get('parent_policy') or '')==normalized(parent):
                shared[other]['parent policy'].add(parent)
    result=[]
    for other,categories in sorted(shared.items()):
        reasons=[('Same parent policy: ' if category=='parent policy' else 'Shared '+category+': ')+', '.join(sorted(values))
                 for category,values in sorted(categories.items())]
        result.append({'relationship_id':f'semantic-shared:{policy_id}:{other}','related_policy_id':other,
            'related_library_policy_id':docs[other].get('library_policy_id'),'related_policy_name':docs[other]['title'],
            'relationship_type':'Related policy context','shared_concepts':sorted({v for values in categories.values() for v in values}),
            'reasons':reasons,'rationale':'; '.join(reasons),'knowledge_fingerprint':matcher.fingerprint})
    return result


def manufactured_controls(policy_id=None):
    """Read explicit manufactured controls regenerated since the current release."""
    from ..database import shared_policy_connection
    with shared_policy_connection() as db:
        rows=db.execute("""SELECT c.*,p.library_policy_id FROM policy_controls c
            JOIN policy_documents p USING(policy_id)
            WHERE c.generated_at >= (SELECT activated_at FROM solution_releases WHERE release_key='semantic-finalization-v1')
              AND (%s::bigint IS NULL OR c.policy_id=%s)
            ORDER BY p.display_order,c.policy_id,c.control_sequence""",(policy_id,policy_id)).fetchall()
    return [{**r,'synthetic':True,'data_origin':'DATA_MANUFACTURING','published_in_graph':False} for r in rows]
