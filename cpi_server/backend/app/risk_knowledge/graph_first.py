"""Operational graph-first extraction; model calls are confined to unresolved spans."""
from datetime import date
import json
from ..services.inventory_schema import GovernedDefinition,GovernedRuleInput
from ..services.rule_governance import store_rule
from .repositories import PostgreSQLRepository
from .policy_representation import build_representation,compile_graph,coverage_summary,representation_id,digest
from .policy_fallback import propose_unresolved,llm_provider

PIPELINE_VERSION='policy-graph-first-v1'


def process_policy(policy_id,user,job_id=None,progress=None,*,fallback_provider=None):
    from ..services.rule_extraction import shared_policy_connection,ingest_policy
    from ..config import POLICY_GRAPH_LLM_FALLBACK,POLICY_GRAPH_FALLBACK_MAX_SPANS,MISTRAL_API_KEY
    repo=PostgreSQLRepository(shared_policy_connection,user['user_id'])
    stages=[{'id':key,'label':label,'status':'Pending'} for key,label in
            [('ingestion','Source ingestion'),('representation','Constrained policy graph'),
             ('fallback','Unresolved interpretation proposals'),('compilation','Graph rule compilation'),('validation','Source and graph validation')]]
    def stage(key,status='Running'):
        next(s for s in stages if s['id']==key)['status']=status
        if progress:progress(0,stage=key,details={'pipeline':PIPELINE_VERSION,'stages':stages})
    stage('ingestion')
    policy,version,document,clauses=ingest_policy(policy_id)
    if not clauses:raise ValueError('Policy source has no extractable passages; restore source text before building a representation')
    stage('ingestion','Completed')
    stage('representation')
    identifier=representation_id(version['id'],document['checksum'])
    rep=repo.get('metadata',identifier)
    if rep is None or rep['source_digest']!=digest([(c['id'],c['source_excerpt']) for c in clauses]):
        previous_digest=rep['content_digest'] if rep else None
        concepts=repo.all('taxonomy_concepts')
        if not concepts:
            from ..config import risk_schema_path
            from .ingestion import parse_schema
            workbook=risk_schema_path()
            if workbook.is_file():
                schema,parsed=parse_schema(workbook.name,workbook.read_bytes())
                repo.put('documents',schema.document_id,schema.model_dump(mode='json'))
                repo.put_many('taxonomy_concepts',[(c.concept_id,c.model_dump(mode='json')) for c in parsed])
                concepts=[c.model_dump(mode='json') for c in parsed]
        rep=build_representation(policy,version,document,clauses,concepts)
        # Persist the graph BEFORE deriving or storing any executable inventory rule.
        if not repo.compare_and_put('metadata',identifier,rep,previous_digest,{'entity_id':identifier,'action':'BUILD_POLICY_REPRESENTATION','notes':'Versioned ontology and whole-span grammar; no LLM extraction'}):
            raise ValueError('Policy representation changed during construction; reload and retry')
    stage('representation','Completed')
    stage('fallback')
    provider=fallback_provider
    if provider is None and POLICY_GRAPH_LLM_FALLBACK and MISTRAL_API_KEY:provider=llm_provider
    if provider and coverage_summary(rep)['unresolved_spans']:
        previous_digest=rep['content_digest']
        propose_unresolved(rep,provider,POLICY_GRAPH_FALLBACK_MAX_SPANS)
        if not repo.compare_and_put('metadata',identifier,rep,previous_digest,{'entity_id':identifier,'action':'PROPOSE_UNRESOLVED_INTERPRETATIONS','notes':'LLM proposals remain unapproved and cannot compile'}):
            raise ValueError('A source review changed the representation during fallback; its decisions were preserved. Reload and retry')
    stage('fallback','Completed')
    stage('compilation')
    definitions=compile_graph(rep,clauses)
    created=[]
    with shared_policy_connection() as connection:
        current=connection.execute("SELECT payload FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=%s FOR SHARE",(identifier,)).fetchone()
        if not current or current['payload']['content_digest']!=rep['content_digest']:
            raise ValueError('Policy interpretation changed before compilation was published; reload and retry')
        # Prevent a source update or stale representation snapshot being published.
        source=connection.execute('SELECT checksum,is_current FROM policy_versions WHERE id=%s FOR SHARE',(version['id'],)).fetchone()
        if not source or not source['is_current'] or source['checksum']!=rep['source_checksum']:
            raise ValueError('Policy source changed during graph compilation')
        from .rule_identity import publish_drafts
        created,changed=publish_drafts(rep,definitions,user,connection,effective_from=version['effective_date'])
        complete=coverage_summary(rep)['complete']
        connection.execute('UPDATE inventory_documents SET extraction_status=%s,processed_at=CURRENT_TIMESTAMP,error=%s WHERE id=%s',
                           ('Completed' if complete else 'Failed',None if complete else 'Policy representation has unresolved source coverage; review required',document['id']))
    for row in created:
        definition=row['definition']
        repo.put('metadata','CPI-RULE-'+str(row['id']),{'pipeline':PIPELINE_VERSION,'status':'GRAPH_COMPILED_'+row['status'].upper(),
            'representation_id':identifier,'representation_node_id':definition['representation_node_id'],
            'representation_digest':rep['content_digest'],'definition_fingerprint':digest(definition),
            'validation':{'source_provenance_verified':True,'graph_compilation_verified':True},
            'source':next(n['provenance'] for n in rep['nodes'] if n['id']==definition['representation_node_id']),
            'job_id':str(job_id) if job_id else None})
    stage('compilation','Completed');stage('validation','Completed')
    coverage=coverage_summary(rep)
    result={'policy_id':policy_id,'policy_name':policy['title'],'pipeline':PIPELINE_VERSION,
            'status':'Completed' if coverage['complete'] else 'Completed with errors',
            'partial_result':not coverage['complete'],'representation_id':identifier,'coverage':coverage,
            'clauses_processed':len(clauses),'clauses_discovered':len(clauses),'rules_proposed':len(created),
            'rule_versions_changed':changed,'rule_versions_unchanged':len(created)-changed,
            'quantitative_rules':sum(d.rule_type=='quantitative' for d in definitions),
            'qualitative_rules':sum(d.rule_type!='quantitative' for d in definitions),
            'rules_approved':0,'manual_review_rules':len(created),'missing_thresholds':0,
            'validation_failures':0,'duplicate_candidates':0,'stages':stages,
            'llm_fallback_spans':rep['fallback']['attempted'],'llm_proposals':rep['fallback']['proposals'],
            'unresolved_spans':coverage['unresolved_spans']}
    if not coverage['complete']:result['error']=f"{coverage['unresolved_spans']} source passages require interpretation or review; overall policy coverage is incomplete. Review each compiled rule's relevant dependencies before operational approval."
    repo.put('metadata','CPI-PIPELINE-'+str(policy_id),result)
    return result
