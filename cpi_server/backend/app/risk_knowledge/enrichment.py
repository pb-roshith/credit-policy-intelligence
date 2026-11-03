"""Enrich saved rule versions without invoking rule extraction or creating versions."""
from .pipeline import PolicyKnowledgePipeline
from .repositories import PostgreSQLRepository
from .service import IntelligenceService
from ..services.automatic_approval import approve_knowledge


def enrich_saved_policy(policy_id,user,connection_factory,provider=None,progress=None,reuse_mappings=False):
    from ..services.policy_ingestion import ingest_policy
    service=IntelligenceService(repository=PostgreSQLRepository(connection_factory,user['user_id']),provider=provider)
    pipeline=PolicyKnowledgePipeline(service,connection_factory,user,progress=progress)
    with connection_factory() as db:
        rows=db.execute("""SELECT r.* FROM policy_rule_versions r JOIN policy_versions pv ON pv.id=r.policy_version_id
            WHERE r.policy_id=%s AND pv.is_current AND r.extraction_key LIKE 'risk-knowledge:%%'
            AND r.status NOT IN ('Rejected','Retired') ORDER BY r.id""",(policy_id,)).fetchall()
    if not rows:
        raise ValueError('No current extracted rules available for enrichment')
    pipeline.stage('schema','Completed')
    approve_knowledge(service)
    pipeline.stage('taxonomy','Completed')
    pipeline.prepare_source(ingest_policy(policy_id))
    selected={row['clause_id'] for row in rows}
    reused=set()
    if reuse_mappings:
        from .models import Clause
        for identifier in selected:
            clause=pipeline.clauses_by_id[identifier]
            saved=service.repo.get('clauses',clause.clause_id)
            if saved and saved['source']['version']==clause.source.version and saved['raw_text']==clause.raw_text:
                pipeline.clauses_by_id[identifier]=Clause.model_validate(saved)
                reused.add(identifier)
    pipeline.classify(selected-reused)
    pipeline.counts['clauses_classified']+=len(reused)
    pipeline.discover_ontology({'CPI-CLAUSE-'+str(identifier) for identifier in selected})
    pipeline.annotate(rows,[clause for clause in pipeline.clauses if clause['id'] in selected],reuse_mappings=reuse_mappings)
    return pipeline.finish({'policy_id':policy_id,'status':'Completed','rules_proposed':len(rows),'rules_created':0})
