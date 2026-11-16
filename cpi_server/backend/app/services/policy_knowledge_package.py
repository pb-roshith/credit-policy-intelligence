"""Portable shared policy knowledge for first deployment; no customer data or AI calls."""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from uuid import uuid4

from psycopg import sql
from psycopg.types.json import Jsonb

from ..config import BASE_DIR, POLICY_OUTPUT_DIR, POLICY_SOURCE_DIR
from ..database import shared_policy_connection
from ..risk_knowledge.semantic_extraction import PIPELINE_VERSION, assemble_graph
from ..risk_knowledge.semantic_model import VERSION, validate_instance
from ..risk_knowledge.semantic_pipeline import current_records, seal
from ..risk_knowledge.repositories import PostgreSQLRepository

PACKAGE_DIR = BASE_DIR / 'policy_knowledge'
FORMAT = 'cpi-policy-knowledge-v1'
MARKER = 'deployment-policy-knowledge-package'
TABLES = ('policy_documents', 'inventory_policies', 'policy_versions',
          'inventory_documents', 'policy_clauses')
CATALOG_FIELDS = ('policy_id', 'policy_code', 'title', 'version', 'policy_category',
                  'parent_policy', 'clause_number', 'display_order', 'document_format',
                  'source_type', 'policy_type', 'library_policy_id', 'effective_date',
                  'status', 'summary', 'page_count', 'file_name')
FIELDS = {
    'policy_documents': CATALOG_FIELDS,
    'inventory_policies': ('id', 'code', 'name'),
    'policy_versions': ('id', 'policy_id', 'version', 'effective_date', 'effective_date_source',
                        'checksum', 'is_current', 'created_at'),
    'inventory_documents': ('id', 'policy_version_id', 'source_document_id', 'file_name',
                            'file_type', 'checksum', 'ingestion_status', 'extraction_status',
                            'ingested_at', 'processed_at', 'error'),
    'policy_clauses': ('id', 'policy_version_id', 'document_id', 'sequence', 'section_heading',
                       'clause_number', 'page_number', 'source_excerpt', 'checksum'),
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      default=lambda x: x.isoformat() if isinstance(x, (date, datetime)) else str(x))


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def local_source(file_name):
    # Packages contain basenames only, never local absolute paths.
    if not isinstance(file_name, str) or not file_name or '/' in file_name or '\\' in file_name or ':' in file_name or file_name in ('.', '..'):
        raise ValueError('Policy source must be a file name without a path')
    candidates = [POLICY_OUTPUT_DIR / file_name, POLICY_SOURCE_DIR / file_name]
    source = next((p for p in candidates if p.is_file()), None)
    if source is None:
        raise ValueError(f'Missing deployed policy source: {file_name}')
    if not source.resolve().is_relative_to(BASE_DIR.resolve()):
        raise ValueError('Policy source is outside the backend directory')
    return source


def schema_source(document):
    name = document['document_name']
    if not isinstance(name, str) or '/' in name or '\\' in name or ':' in name or not name.endswith('.xlsx'):
        raise ValueError('Invalid schema workbook name')
    source = BASE_DIR / 'risk_schema' / name
    if not source.is_file() or not source.resolve().is_relative_to(BASE_DIR.resolve()) or checksum(source.read_bytes()) != document['checksum']:
        raise ValueError(f'Missing or changed taxonomy schema workbook: {name}')
    return source


def database_fingerprint(connection):
    """Small database-side digests detect committed changes without exporting files."""
    parts = []
    for table in TABLES:
        key = 'policy_id' if table == 'policy_documents' else 'id'
        row = connection.execute(sql.SQL("SELECT md5(COALESCE(string_agg(md5(row_to_json(t)::text), ',' ORDER BY {}), '')) AS digest FROM {} t").format(
            sql.Identifier(key), sql.Identifier(table))).fetchone()
        parts.append(row['digest'])
    row = connection.execute("""SELECT md5(COALESCE(string_agg(kind || ':' || id || ':' || md5(payload::text), ',' ORDER BY kind,id), '')) AS digest
        FROM risk_knowledge_objects WHERE owner_id='' AND
        (kind IN ('taxonomy_concepts','ontology_relationships') OR
         (kind='documents' AND payload->>'document_type'='schema') OR
         (kind='metadata' AND payload->>'kind'='semantic_policy'))""").fetchone()
    parts.append(row['digest'])
    return checksum('|'.join(parts).encode())


def export_package(directory=PACKAGE_DIR, connection_factory=shared_policy_connection):
    directory = Path(directory)
    # All rows and semantic records must come from one consistent snapshot.
    with connection_factory() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if not c.execute("SELECT pg_try_advisory_xact_lock(hashtext('policy-knowledge-export')) AS acquired").fetchone()['acquired']:
            raise ValueError('Another policy knowledge export is running; retry shortly')
        fingerprint = database_fingerprint(c)
        from contextlib import contextmanager
        @contextmanager
        def snapshot():
            yield c
        records = current_records(PostgreSQLRepository(snapshot, None))
        if not records:
            raise ValueError('No current semantic policy knowledge to export')
        policy_ids = [r['policy_id'] for r in records]
        version_ids = [r['policy_version_id'] for r in records]
        rows = {
            'policy_documents': c.execute('SELECT * FROM policy_documents WHERE policy_id=ANY(%s) ORDER BY policy_id', (policy_ids,)).fetchall(),
            'inventory_policies': c.execute('SELECT * FROM inventory_policies WHERE id=ANY(%s) ORDER BY id', (policy_ids,)).fetchall(),
            'policy_versions': c.execute('SELECT * FROM policy_versions WHERE id=ANY(%s) ORDER BY id', (version_ids,)).fetchall(),
            'inventory_documents': c.execute('SELECT * FROM inventory_documents WHERE policy_version_id=ANY(%s) ORDER BY id', (version_ids,)).fetchall(),
            'policy_clauses': c.execute('SELECT * FROM policy_clauses WHERE policy_version_id=ANY(%s) ORDER BY id', (version_ids,)).fetchall(),
        }
        objects = c.execute("""SELECT kind,id,payload FROM risk_knowledge_objects WHERE owner_id=''
            AND (kind IN ('taxonomy_concepts','ontology_relationships') OR
                 (kind='documents' AND payload->>'document_type'='schema')) ORDER BY kind,id""").fetchall()
        for obj in objects:
            if obj['kind'] == 'documents':
                obj['payload']['metadata'].pop('registered_path', None)
        payload = {'format': FORMAT, 'ontology_version': VERSION, 'pipeline_version': PIPELINE_VERSION,
                   'database_fingerprint': fingerprint,
                   'exported_at': datetime.now(timezone.utc).isoformat(),
                   'tables': {table: [{k: row[k] for k in FIELDS[table]} for row in rows[table]] for table in TABLES},
                   'records': records, 'objects': objects,
                   'sources': {p['file_name']: checksum(local_source(p['file_name']).read_bytes()) for p in rows['policy_documents']}}
        # Round-trip dates into the same representation an importer will read.
        payload = json.loads(encoded(payload))
        validate_package(payload)
        data = (encoded(payload) + '\n').encode('utf-8')
        directory.mkdir(parents=True, exist_ok=True)
        # One self-checking file avoids partially written manifest/data pairs.
        envelope = {'sha256': checksum(data), 'payload': payload}
        temporary = directory / ('knowledge.' + uuid4().hex + '.tmp')
        try:
            temporary.write_text(encoded(envelope) + '\n', encoding='utf-8')
            temporary.replace(directory / 'knowledge.json')
        finally:
            temporary.unlink(missing_ok=True)
        return {**summary(payload), 'database_fingerprint': fingerprint}


def summary(payload):
    graph = assemble_graph(payload['records'])
    return {'policies': len(payload['records']), 'rules': sum(len(r['rules']) for r in payload['records']),
            'graph_nodes': len(graph['nodes']), 'graph_relationships': len(graph['relationships'])}


def validate_package(payload):
    if payload.get('format') != FORMAT or payload.get('ontology_version') != VERSION or payload.get('pipeline_version') != PIPELINE_VERSION:
        raise ValueError('Knowledge package format, ontology or extraction pipeline is incompatible')
    if set(payload['tables']) != set(TABLES) or not payload['records']:
        raise ValueError('Incomplete knowledge package')
    by_table = {}
    for table in TABLES:
        fields = set(FIELDS[table])
        id_key = 'policy_id' if table == 'policy_documents' else 'id'
        rows = payload['tables'][table]
        if any(set(row) != fields for row in rows):
            raise ValueError(f'Unexpected columns in {table}')
        keys = [row[id_key] for row in rows]
        if any(type(key) is not int or key < 1 for key in keys) or len(set(keys)) != len(keys):
            raise ValueError(f'Invalid or duplicate IDs in {table}')
        by_table[table] = {row[id_key]: row for row in rows}
    policies = by_table['policy_documents']
    versions = by_table['policy_versions']
    documents = by_table['inventory_documents']
    clauses = by_table['policy_clauses']
    if set(by_table['inventory_policies']) != set(policies) or len(payload['records']) != len(policies):
        raise ValueError('Every packaged policy needs a matching inventory and semantic record')
    if set(payload['sources']) != {p['file_name'] for p in policies.values()}:
        raise ValueError('Policy source manifest is incomplete')
    for policy in policies.values():
        source = local_source(policy['file_name'])
        if checksum(source.read_bytes()) != payload['sources'][policy['file_name']]:
            raise ValueError(f"Policy source changed: {policy['file_name']}")
    for version in versions.values():
        policy = policies.get(version['policy_id'])
        if not policy or not version['is_current'] or version['version'] != policy['version'] or version['checksum'] != payload['sources'][policy['file_name']]:
            raise ValueError('Policy version does not match its deployed source')
    for doc in documents.values():
        version = versions.get(doc['policy_version_id'])
        if not version or doc['source_document_id'] != version['policy_id'] or doc['checksum'] != version['checksum'] or doc['ingestion_status'] != 'Completed':
            raise ValueError('Inventory document does not match its policy version')
    for clause in clauses.values():
        doc = documents.get(clause['document_id'])
        if not doc or clause['policy_version_id'] != doc['policy_version_id'] or checksum(clause['source_excerpt'].encode()) != clause['checksum']:
            raise ValueError('Evidence passage identity or checksum is invalid')
    seen = set()
    for record in payload['records']:
        pid = record['policy_id']
        version = versions.get(record['policy_version_id'])
        if pid in seen or pid not in policies or not version or version['policy_id'] != pid or record['id'] != f'SEMANTIC-POLICY-{pid}':
            raise ValueError('Semantic policy identity is invalid')
        seen.add(pid)
        if record.get('ontology_version') != VERSION or record.get('pipeline') != PIPELINE_VERSION or record['source_checksum'] != version['checksum'] or record['policy_version'] != version['version']:
            raise ValueError('Semantic knowledge does not match the policy source')
        if seal(deepcopy(record))['content_digest'] != record['content_digest']:
            raise ValueError('Semantic record checksum is invalid')
        expected = [c for c in clauses.values() if c['policy_version_id'] == version['id']]
        expected.sort(key=lambda c: (c['sequence'], c['id']))
        projected = [{k: c.get(k) for k in ('id','sequence','source_excerpt','section_heading','clause_number','page_number')} for c in expected]
        if record['source_clauses'] != projected:
            raise ValueError('Semantic evidence does not match stored source passages')
        from ..risk_knowledge.semantic_extraction import digest, ExtractedRule, rule_id
        if record['source_digest'] != digest([(c['id'], c['source_excerpt']) for c in expected]):
            raise ValueError('Semantic source fingerprint is invalid')
        rule_ids = set()
        for rule in record['rules']:
            extracted = ExtractedRule.model_validate(rule['extracted'])
            if rule['id'] in rule_ids or rule['id'] != rule_id(version['id'], extracted.clause_id, extracted.rule_sequence):
                raise ValueError('Duplicate or invalid semantic rule ID')
            rule_ids.add(rule['id'])
            if extracted.clause_id not in {c['id'] for c in expected} or rule['status'] not in ('APPROVED','PROPOSED','REJECTED'):
                raise ValueError('Invalid semantic rule source or review status')
    seen_objects = set()
    for obj in payload['objects']:
        key = (obj['kind'], obj['id'])
        if obj['kind'] not in ('taxonomy_concepts', 'ontology_relationships', 'documents') or key in seen_objects:
            raise ValueError('Unsupported or duplicate shared knowledge object')
        if obj['kind'] == 'documents':
            if obj['payload']['document_type'] != 'schema' or obj['payload']['document_id'] != obj['id']:
                raise ValueError('Only shared taxonomy schema documents may be packaged')
            schema_source(obj['payload'])
        seen_objects.add(key)
    validation = validate_instance(assemble_graph(payload['records']))
    if not validation['conforms']:
        raise ValueError('Packaged knowledge graph violates the ontology: ' + str(validation['errors'][:3]))


def read_package(directory=PACKAGE_DIR):
    envelope = json.loads((Path(directory) / 'knowledge.json').read_text(encoding='utf-8'))
    payload = envelope['payload']
    if checksum((encoded(payload) + '\n').encode('utf-8')) != envelope['sha256']:
        raise ValueError('Knowledge package checksum is invalid')
    validate_package(payload)
    return envelope


def import_package(directory=PACKAGE_DIR, connection_factory=shared_policy_connection, dry_run=False):
    envelope = read_package(directory)
    payload = envelope['payload']
    with connection_factory() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('policy-knowledge-package'))")
        marker = c.execute("SELECT payload FROM risk_knowledge_objects WHERE kind='metadata' AND owner_id='' AND id=%s", (MARKER,)).fetchone()
        if marker:
            if marker['payload']['sha256'] != envelope['sha256']:
                raise ValueError('A different knowledge package was already imported; existing knowledge is preserved')
            return {'status': 'already imported', **summary(payload)}
        # Stable IDs retain every rule/reference/evidence link. This is a seed,
        # not a merge operation; never overwrite operational policy knowledge.
        c.execute(sql.SQL('LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE').format(
            sql.SQL(',').join(sql.Identifier(t) for t in (*TABLES, 'risk_knowledge_objects'))))
        for table in TABLES:
            if c.execute(sql.SQL('SELECT 1 FROM {} LIMIT 1').format(sql.Identifier(table))).fetchone():
                raise ValueError(f'Knowledge import requires an empty policy catalog/inventory; {table} is populated')
        if c.execute("SELECT 1 FROM risk_knowledge_objects WHERE kind='metadata' AND payload->>'kind'='semantic_policy' LIMIT 1").fetchone():
            raise ValueError('Existing semantic knowledge will not be overwritten')
        for obj in payload['objects']:
            existing = c.execute("SELECT payload FROM risk_knowledge_objects WHERE owner_id='' AND kind=%s AND id=%s", (obj['kind'], obj['id'])).fetchone()
            if existing and existing['payload'] != obj['payload']:
                raise ValueError('Existing taxonomy/ontology differs from the package')
        if dry_run:
            return {'status': 'validated; no changes', **summary(payload)}
        for table in TABLES:
            for original in payload['tables'][table]:
                row = dict(original)
                if table == 'policy_documents':
                    row.update(local_pdf_path=str(local_source(row['file_name']).resolve()),
                               mistral_document_id='local-registration:' + row['policy_code'],
                               mistral_library_id='local-registration', mistral_agent_id='local-registration')
                elif table == 'inventory_documents':
                    row['source_path'] = str(local_source(row['file_name']).resolve())
                columns = list(row)
                c.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                    sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, columns)),
                    sql.SQL(',').join(sql.Placeholder() for _ in columns)), [row[k] for k in columns])
        for obj in payload['objects']:
            value = deepcopy(obj['payload'])
            if obj['kind'] == 'documents':
                value['metadata']['registered_path'] = str(schema_source(value).resolve())
            c.execute("INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES (%s,'',%s,%s) ON CONFLICT DO NOTHING", (obj['kind'], obj['id'], Jsonb(value)))
        if any(obj['kind'] == 'documents' for obj in payload['objects']):
            # Do not let first-use workbook ingestion overwrite restored reviews.
            c.execute("INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES ('metadata','','schema_initialized',%s) ON CONFLICT DO NOTHING", (Jsonb({'source_schema_only': True}),))
        for record in payload['records']:
            c.execute("INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES ('metadata','',%s,%s)", (record['id'], Jsonb(record)))
        # Advance serial sequences after restoring explicit source IDs.
        for table in ('policy_documents', 'policy_versions', 'inventory_documents', 'policy_clauses'):
            key = 'policy_id' if table == 'policy_documents' else 'id'
            c.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s,%s), (SELECT MAX({}) FROM {}), true)").format(sql.Identifier(key), sql.Identifier(table)), (table, key))
        c.execute("INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES ('metadata','',%s,%s)",
                  (MARKER, Jsonb({'sha256': envelope['sha256'], 'imported_at': datetime.now(timezone.utc).isoformat(), **summary(payload)})))
        c.execute("INSERT INTO audit_events(entity_type,entity_id,new_value,action,actor,reason) VALUES ('PolicyKnowledgePackage',%s,%s,'Import','system:knowledge-package','Imported source-verified shared knowledge; original rule and scope review histories retained')",
                  (envelope['sha256'], Jsonb(summary(payload))))
    return {'status': 'imported', **summary(payload)}


def autoload_package():
    """Seed only a fresh deployment. Existing installations are never modified."""
    import os
    if os.getenv('POLICY_KNOWLEDGE_AUTO_IMPORT', 'true').lower() not in ('true', '1', 'yes'):
        return
    if not (PACKAGE_DIR / 'knowledge.json').is_file():
        return
    with shared_policy_connection() as c:
        if c.execute('SELECT 1 FROM policy_documents LIMIT 1').fetchone():
            return
    result = import_package()
    logging.getLogger(__name__).info('Bundled policy knowledge: %s', encoded(result))
