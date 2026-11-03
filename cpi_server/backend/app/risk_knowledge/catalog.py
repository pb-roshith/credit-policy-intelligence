"""Read-only graph projection of CPI's existing policy inventory and governed rules."""
import json
from pathlib import Path
from .ingestion import uid


def read_catalog(connection_factory):
    with connection_factory() as db:
        policies = db.execute('SELECT policy_id,title,file_name,document_format,version,effective_date,status,source_type,summary,local_pdf_path FROM policy_documents ORDER BY display_order,policy_id').fetchall()
        clauses = db.execute('''SELECT cl.*,pv.policy_id,pv.version,doc.file_name,doc.source_path,doc.checksum,
                              p.title,p.source_type FROM policy_clauses cl JOIN policy_versions pv ON pv.id=cl.policy_version_id
                              JOIN inventory_documents doc ON doc.id=cl.document_id JOIN policy_documents p ON p.policy_id=pv.policy_id
                              ORDER BY cl.id''').fetchall()
        rules = db.execute('''SELECT r.*,e.rule_code,p.title,cl.source_excerpt,cl.section_heading,cl.clause_number,cl.page_number,
                            cl.document_id AS inventory_document_id,rk.payload AS risk_knowledge,
                            (r.policy_version_id IS NULL OR NOT COALESCE(pv.is_current,false)
                             OR p.version<>r.policy_version OR md5(p.summary)<>r.policy_fingerprint) AS review_required
                            FROM policy_rule_versions r JOIN policy_documents p USING(policy_id)
                            LEFT JOIN policy_rule_entities e ON e.id=r.rule_entity_id
                            LEFT JOIN policy_clauses cl ON cl.id=r.clause_id LEFT JOIN policy_versions pv ON pv.id=r.policy_version_id
                            LEFT JOIN risk_knowledge_objects rk ON rk.kind='metadata' AND rk.owner_id='' AND rk.id='CPI-RULE-'||r.id::text
                            WHERE NOT EXISTS(SELECT 1 FROM policy_rule_versions newer WHERE newer.rule_key=r.rule_key AND newer.version>r.version)
                            ORDER BY r.id''').fetchall()
    return policies, clauses, rules


def documents_from_catalog(policies, clauses):
    result = []
    for p in policies:
        source_clauses = [c for c in clauses if c['policy_id'] == p['policy_id'] and c['version'] == p['version']]
        result.append({'document_id': 'CPI-POLICY-' + str(p['policy_id']), 'document_name': p['title'],
                       'document_type': 'policy', 'format': p.get('document_format') or Path(p.get('file_name') or '').suffix.lstrip('.') or 'UNKNOWN',
                       'checksum': 'UNKNOWN', 'raw_text': '\n\n'.join(c['source_excerpt'] for c in source_clauses) or p.get('summary') or '',
                       'version': p['version'], 'effective_date': str(p['effective_date']) if p.get('effective_date') else None,
                       'synthetic': any(term in str(p.get('source_type', '')).lower() for term in ('synthetic','manufactured')),
                       'metadata': {'existing_policy_id': p['policy_id'], 'registered_path': p.get('local_pdf_path'), 'original_file_name': p.get('file_name'),
                                    'catalog_source_type': p.get('source_type'), 'catalog_status': p['status'],
                                    'raw_text_is_catalog_summary': not bool(source_clauses)}})
    return result


def project_catalog(graph, policies, clauses, rules, annotations=None):
    snapshot = graph.snapshot()
    nodes = {n['id']: n for n in snapshot['nodes']}
    edges = list(snapshot['edges'])
    source_by_clause = {}
    def node(identifier, label, kind, status, provenance, payload=None):
        nodes[identifier] = {'id': identifier, 'label': label, 'type': kind, 'status': status,
                             'risk_domain': 'UNKNOWN', 'source_name': provenance['document_name'],
                             'provenance': provenance, 'payload': payload}
    def edge(subject, predicate, target, provenance, status='SOURCE'):
        edges.append({'id': uid('CPI-EDGE-', f'{subject}|{predicate}|{target}'), 'source': subject,
                      'target': target, 'predicate': predicate, 'provenance': provenance, 'status': status})
    for p in policies:
        source = {'document_id': 'CPI-POLICY-' + str(p['policy_id']), 'document_name': p['title'],
                  'origin': 'CPI_POLICY_CATALOG', 'passage': p.get('summary') or p['title'],
                  'version': p['version'], 'effective_date': str(p['effective_date']) if p.get('effective_date') else None}
        node(source['document_id'], p['title'], 'PolicyDocument', 'SOURCE', source)
    for c in clauses:
        source = {'document_id': 'CPI-POLICY-' + str(c['policy_id']), 'document_name': c['title'],
                  'origin': 'CPI_INVENTORY_CLAUSE', 'passage': c['source_excerpt'], 'version': c['version'],
                  'section': c.get('section_heading'), 'page': c.get('page_number'), 'clause': c.get('clause_number'),
                  'inventory_document_id': c['document_id']}
        source_by_clause[c['id']] = source
        clause_id = 'CPI-CLAUSE-' + str(c['id'])
        node(clause_id, 'Clause ' + str(c.get('clause_number') or c['sequence']), 'PolicyClause', 'SOURCE', source, c['source_excerpt'])
        edge(source['document_id'], 'CONTAINS', clause_id, source)
    for r in rules:
        # Only exact inventory clauses establish DERIVED_FROM. No synthetic clause is invented.
        source = source_by_clause.get(r['clause_id'])
        if not source:
            source = {'document_id': 'CPI-POLICY-' + str(r['policy_id']), 'document_name': r['title'],
                      'origin': 'CPI_RULE_INVENTORY', 'passage': r['definition'].get('source_excerpt') or 'Exact clause link unavailable', 'version': r['policy_version']}
        identifier = 'CPI-RULE-' + str(r['id'])
        label = r['definition'].get('rule_name') or r.get('rule_code') or identifier
        annotation=(annotations or {}).get(r['id']) or r.get('risk_knowledge')
        node(identifier, label, 'GovernedPolicyRule', r['status'].upper().replace(' ', '_'), source,
             {'rule_version_id': r['id'], 'active': r['active'], 'review_required': r['review_required'], 'definition': r['definition'],
              'risk_knowledge':annotation})
        if annotation:
            for mapping in annotation.get('taxonomy_mappings',[]):
                target=mapping.get('concept_id')
                if mapping.get('status')=='RESOLVED' and target in nodes and nodes[target]['status']=='APPROVED':
                    edge(identifier,'MAPS_TO',target,annotation['source'],r['status'].upper())
        if r['clause_id'] in source_by_clause:
            edge(identifier, 'DERIVED_FROM', 'CPI-CLAUSE-' + str(r['clause_id']), source, r['status'].upper())
        else:
            edge(source['document_id'], 'CONTAINS', identifier, source)
        condition = r['definition'].get('applicability_conditions')
        if condition:
            cid = identifier + ':scope'
            node(cid, 'Structured applicability scope', 'Condition', r['status'].upper(), source, condition)
            edge(identifier, 'HAS_CONDITION', cid, source, r['status'].upper())
        approval = r['definition'].get('approval_or_escalation_requirement')
        if approval:
            aid = identifier + ':approval'
            node(aid, approval, 'ApprovalRequirement', r['status'].upper(), source, approval)
            edge(identifier, 'REQUIRES', aid, source, r['status'].upper())
    graph.replace(list(nodes.values()), list({e['id']:e for e in edges}.values()))
