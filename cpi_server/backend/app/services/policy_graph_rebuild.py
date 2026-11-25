"""Build and store a validated snapshot of the shared reviewed policy graph."""
from psycopg.types.json import Jsonb

from ..risk_knowledge.competency_queries import coverage
from ..risk_knowledge.semantic_model import validate_instance


def rebuild_summary(matcher):
    validation = validate_instance(matcher.graph)
    if not validation['conforms']:
        raise ValueError('Rebuilt policy graph failed ontology validation')
    findings = coverage(matcher)
    return {'ontology_version': matcher.graph['ontology_version'], 'counts': validation['counts'],
            'candidate_count': len(findings['relationship_candidates']) + len(findings['source_relationship_candidates']),
            'policy_count': findings['policies'], 'source_passages': findings['source_passages']}


def store_snapshot(connection, matcher, summary, *, job_id=None):
    snapshot = {'job_id': job_id, 'knowledge_fingerprint': matcher.fingerprint,
                'summary': summary, 'instance': matcher.graph}
    connection.execute("""INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES
        ('semantic_graph_snapshot','','current',%s) ON CONFLICT(kind,owner_id,id)
        DO UPDATE SET payload=EXCLUDED.payload""", (Jsonb(snapshot),))
