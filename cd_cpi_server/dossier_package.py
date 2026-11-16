"""Portable company catalog and original documents; no deals or narratives."""
from contextlib import contextmanager, closing
from datetime import date, datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / 'credit_dossier_backend'
DEFAULT_DIRECTORY = BACKEND / 'dossier_data'
FORMAT = 'credit-dossier-companies-documents-v2'
MANIFEST = 'companies.json'
TABLES = ('public.mcp_companies', 'public.mcp_documents')
COMPANY_FIELDS = ('id','owner_user_id','name','normalized_name','industry','geography',
                  'segment','kyc_status','mistral_library_id','created_at','updated_at')
DOCUMENT_FIELDS = ('id','company_id','document_number','document_name','local_path',
                   'mistral_document_id','summary','processing_status','created_at',
                   'updated_at','generator_version')


def directory():
    return Path(os.getenv('DOSSIER_DATA_DIR') or DEFAULT_DIRECTORY)


def encode(value):
    def convert(item):
        if isinstance(item, (datetime, date)):
            return item.isoformat()
        raise TypeError(f'Unsupported package value: {type(item).__name__}')
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, default=convert)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identifier(name):
    return sql.Identifier(*name.split('.'))


def configuration():
    from dotenv import dotenv_values
    return {**dotenv_values(BACKEND / '.env'),
            **dotenv_values(ROOT / 'credit_dossier_mcp' / '.env'), **os.environ}


@contextmanager
def mcp_connection():
    values = configuration()
    url = values.get('MCP_DATABASE_URL')
    arguments = {'conninfo': url} if url else {
        'host': values.get('POSTGRES_HOST', '127.0.0.1'),
        'port': int(values.get('POSTGRES_PORT', '5432')),
        'dbname': values.get('POSTGRES_DB', 'cpi_credit_dossier_mcp'),
        'user': values.get('POSTGRES_USER', 'postgres'),
        'password': values.get('POSTGRES_PASSWORD', 'root'),
    }
    with psycopg.connect(**arguments, row_factory=dict_row) as c:
        yield c


def asset_path(folder, key):
    if not isinstance(key, str) or not key.startswith('files/') or '\\' in key:
        raise ValueError('Invalid document asset path')
    target = (Path(folder) / key).resolve()
    if not target.is_relative_to((Path(folder) / 'files').resolve()):
        raise ValueError('Document asset escapes its package folder')
    return target


def add_asset(folder, assets, content, filename):
    if not content:
        raise ValueError('Cannot package an empty original document')
    suffix = Path(filename).suffix.lower()
    if suffix not in ('.pdf','.docx','.xlsx','.pptx','.txt','.csv','.md','.json','.png','.jpg','.jpeg'):
        suffix = '.bin'
    sha = digest(content)
    key = f'files/{sha}{suffix}'
    target = asset_path(folder, key)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or digest(target.read_bytes()) != sha:
        temporary = target.with_name(target.name + '.' + uuid4().hex + '.tmp')
        try:
            temporary.write_bytes(content)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    assets[key] = {'sha256': sha, 'size': len(content)}
    return key


def gemini_store_path():
    return Path(configuration().get('GEMINI_STORE_PATH') or ROOT.parent / '.ai-data' / 'gemini.sqlite3')


def local_resource(resource_id, kind):
    path = gemini_store_path()
    if not path.is_file():
        return None
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as c:
        row = c.execute('SELECT metadata,content,parent FROM resources WHERE id=? AND kind=?', (resource_id, kind)).fetchone()
    return row


def download_original(library_id, document_id):
    local = local_resource(document_id, 'document')
    if local:
        if local[2] != library_id:
            raise ValueError('Document belongs to another provider library')
        return local[1]
    # Preserve originals left in the previous Mistral account after switching AI
    # providers. The original key remains in the environment; never package it.
    from mistralai.client import Mistral
    import httpx
    key = configuration().get('MISTRAL_API_KEY', '')
    if not key:
        raise ValueError('Original document is not local; configure its Mistral account key to export it')
    with Mistral(api_key=key, timeout_ms=30000) as client:
        url = client.beta.libraries.documents.get_signed_url(library_id=library_id, document_id=document_id)
        with httpx.stream('GET', url, follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 50 * 1024 * 1024:
                    raise ValueError('Original document exceeds the 50 MB package limit')
            return bytes(content)


def export_package(folder=None, mcp_factory=mcp_connection):
    folder = Path(folder or directory())
    assets = {}
    with mcp_factory() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        companies = c.execute('SELECT * FROM mcp_companies ORDER BY id').fetchall()
        documents = c.execute('SELECT * FROM mcp_documents ORDER BY id').fetchall()
    if not companies:
        raise ValueError('There are no companies to export')
    # Deliberate allowlists exclude company context/financial datasets and any
    # future columns carrying generated workflow content.
    companies = [{k: r[k] for k in COMPANY_FIELDS} for r in companies]
    documents = [{k: r[k] for k in DOCUMENT_FIELDS} for r in documents]
    cached = {}
    for name in (MANIFEST, 'deals.json'):
        path = folder / name
        if path.is_file():
            prior = json.loads(path.read_text(encoding='utf-8'))
            if digest(encode(prior['payload']).encode()) != prior['sha256']:
                raise ValueError('Cached document package checksum is invalid')
            for resource in prior['payload']['provider_documents']:
                cached[(resource['library_id'],resource['document_id'])] = (resource,prior['payload']['assets'][resource['asset']])
    resources = []
    companies_by_id = {r['id']:r for r in companies}
    for index, doc in enumerate(documents, 1):
        company = companies_by_id[doc['company_id']]
        library, doc_id = company['mistral_library_id'], doc['mistral_document_id']
        if not library or not doc_id:
            raise ValueError('A company document has no reusable provider identity')
        old = cached.get((library,doc_id))
        if old:
            resource, info = old
            content = asset_path(folder, resource['asset']).read_bytes()
            if digest(content) != info['sha256'] or len(content) != info['size']:
                raise ValueError('Cached original document checksum is invalid')
        elif doc.get('local_path') and Path(doc['local_path']).is_file():
            content = Path(doc['local_path']).read_bytes()
        else:
            content = download_original(library,doc_id)
        key = add_asset(folder,assets,content,doc['document_name'])
        resources.append({'library_id':library,'document_id':doc_id,'filename':doc['document_name'],'asset':key})
        doc['local_path'] = 'asset:' + key
        if index % 10 == 0:
            print(f'Captured {index}/{len(documents)} original company documents',flush=True)
    payload = json.loads(encode({'format':FORMAT,'exported_at':datetime.now(timezone.utc),
        'mcp':{'public.mcp_companies':companies,'public.mcp_documents':documents},
        'provider_documents':resources,'assets':assets}))
    validate_payload(payload,folder)
    envelope = {'sha256':digest(encode(payload).encode()),'payload':payload}
    folder.mkdir(parents=True,exist_ok=True)
    temporary = folder / ('companies.' + uuid4().hex + '.tmp')
    try:
        temporary.write_text(encode(envelope) + '\n',encoding='utf-8')
        temporary.replace(folder / MANIFEST)
    finally:
        temporary.unlink(missing_ok=True)
    # Remove the superseded export containing deals/narratives only after the
    # replacement catalog and all original documents validate successfully.
    (folder / 'deals.json').unlink(missing_ok=True)
    return counts(payload)


def counts(payload):
    return {'companies':len(payload['mcp']['public.mcp_companies']),
            'company_documents':len(payload['mcp']['public.mcp_documents']),
            'original_files':len(payload['assets'])}


def validate_payload(payload,folder):
    if set(payload) != {'format','exported_at','mcp','provider_documents','assets'} or payload.get('format') != FORMAT or set(payload['mcp']) != set(TABLES):
        raise ValueError('Package must contain only company catalog and document data')
    companies = payload['mcp']['public.mcp_companies']
    documents = payload['mcp']['public.mcp_documents']
    if not companies:
        raise ValueError('Company catalog is empty')
    for table, fields in (('public.mcp_companies',COMPANY_FIELDS),('public.mcp_documents',DOCUMENT_FIELDS)):
        rows = payload['mcp'][table]
        ids = [r['id'] for r in rows]
        if any(type(i) is not int or i < 1 for i in ids) or len(set(ids)) != len(ids) or any(set(r) != set(fields) for r in rows):
            raise ValueError('Invalid or extra company/document columns or IDs')
    for key, info in payload['assets'].items():
        data = asset_path(folder,key).read_bytes()
        if len(data) != info['size'] or digest(data) != info['sha256']:
            raise ValueError('Original document checksum is invalid')
    companies = {r['id']:r for r in companies}
    resources = {}
    for resource in payload['provider_documents']:
        if set(resource) != {'library_id','document_id','filename','asset'} or resource['asset'] not in payload['assets']:
            raise ValueError('Invalid provider document original')
        key = (resource['library_id'],resource['document_id'])
        if key in resources:
            raise ValueError('Duplicate provider document')
        resources[key] = resource
    used = set()
    owner_names = set()
    for company in companies.values():
        identity = (company['owner_user_id'],company['normalized_name'])
        if not company['owner_user_id'] or identity in owner_names:
            raise ValueError('Invalid company ownership or duplicate company name')
        owner_names.add(identity)
    for doc in documents:
        company = companies.get(doc['company_id'])
        if not company:
            raise ValueError('Document references a missing company')
        key = (company['mistral_library_id'],doc['mistral_document_id'])
        resource = resources.get(key)
        if not resource or doc['local_path'] != 'asset:' + resource['asset'] or doc['document_name'] != resource['filename']:
            raise ValueError('Company document is missing its matching original')
        used.add(key)
    if used != set(resources) or {r['asset'] for r in resources.values()} != set(payload['assets']):
        raise ValueError('Package contains unrelated documents')


def read_package(folder=None):
    folder = Path(folder or directory())
    value = json.loads((folder / MANIFEST).read_text(encoding='utf-8'))
    if digest(encode(value['payload']).encode()) != value['sha256']:
        raise ValueError('Dossier package checksum is invalid')
    validate_payload(value['payload'], folder)
    return value


def restore_gemini(payload, folder, store_path=None):
    """Restore source libraries only, preserving IDs without copying conversations."""
    target = Path(store_path or gemini_store_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target)) as c, c:
        c.execute('CREATE TABLE IF NOT EXISTS resources (id TEXT PRIMARY KEY, kind TEXT, parent TEXT, metadata TEXT, content BLOB)')
        for resource in payload['provider_documents']:
            library, document = resource['library_id'], resource['document_id']
            content = asset_path(folder, resource['asset']).read_bytes()
            for rid, kind, parent, metadata, blob in (
                (library, 'library', None, {'id': library, 'name': 'Restored Dossier company documents'}, None),
                (document, 'document', library, {'id': document, 'name': resource['filename'], 'file_name': resource['filename'],
                    'mime_type': mimetypes.guess_type(resource['filename'])[0] or 'application/octet-stream', 'processing_status': 'completed'}, content),
            ):
                existing = c.execute('SELECT kind,parent,content FROM resources WHERE id=?', (rid,)).fetchone()
                if existing:
                    if existing[0] != kind or existing[1] != parent or (kind == 'document' and existing[2] != blob):
                        raise ValueError('Existing AI document conflicts with the deployment package')
                else:
                    c.execute('INSERT INTO resources VALUES (?,?,?,?,?)', (rid, kind, parent, encode(metadata), blob))


def _insert(c, name, row):
    schema, table = name.split('.')
    allowed = {r['column_name'] for r in c.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s', (schema, table)).fetchall()}
    if not set(row) <= allowed:
        raise ValueError(f'Package columns are incompatible with {name}')
    columns = list(row)
    values = [Jsonb(row[k]) if isinstance(row[k], (dict,list)) else row[k] for k in columns]
    c.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(identifier(name),
              sql.SQL(',').join(map(sql.Identifier, columns)), sql.SQL(',').join(sql.Placeholder() for _ in columns)), values)


def _marker(c, name, sha, dry_run=False):
    if dry_run and not c.execute('SELECT to_regclass(%s) AS relation', (name,)).fetchone()['relation']:
        return False
    c.execute(sql.SQL('CREATE TABLE IF NOT EXISTS {} (id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW())').format(identifier(name)))
    existing = c.execute(sql.SQL('SELECT sha256 FROM {} WHERE id=1').format(identifier(name))).fetchone()
    if existing and existing['sha256'] != sha:
        raise ValueError('A different Dossier package was already loaded; existing data is preserved')
    return bool(existing)


def import_mcp(folder=None, factory=mcp_connection, dry_run=False, ai_provider=None):
    folder = Path(folder or directory())
    envelope = read_package(folder)
    payload = envelope['payload']
    with factory() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('dossier-data-mcp-import'))")
        if _marker(c, 'public.dossier_mcp_data_import', envelope['sha256'], dry_run):
            return {'status': 'already imported', **counts(payload)}
        names = TABLES
        c.execute(sql.SQL('LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE').format(sql.SQL(',').join(identifier(t) for t in names)))
        for name in names:
            if c.execute(sql.SQL('SELECT 1 FROM {} LIMIT 1').format(identifier(name))).fetchone():
                raise ValueError('Dossier import requires empty MCP company/document tables')
        if dry_run:
            return {'status': 'validated; no company changes', **counts(payload)}
        if (ai_provider or os.getenv('AI_PROVIDER', 'mistral')).lower() == 'gemini':
            restore_gemini(payload, folder)
        for name in names:
            for original in payload['mcp'][name]:
                row = dict(original)
                if name == 'public.mcp_documents':
                    row['local_path'] = str(asset_path(folder, row['local_path'][6:]))
                _insert(c, name, row)
            c.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s,'id'), COALESCE((SELECT max(id) FROM {}),1), EXISTS(SELECT 1 FROM {}))").format(identifier(name), identifier(name)), (name,))
        c.execute('INSERT INTO public.dossier_mcp_data_import(id,sha256) VALUES (1,%s)', (envelope['sha256'],))
    return {'status': 'imported', **counts(payload)}


def autoload_mcp(factory=mcp_connection):
    if os.getenv('DOSSIER_DATA_AUTO_IMPORT', 'true').lower() not in ('1','true','yes') or not (directory() / MANIFEST).is_file():
        return None
    with factory() as c:
        if c.execute('SELECT 1 FROM mcp_companies LIMIT 1').fetchone():
            return None
    return import_mcp(factory=factory)
