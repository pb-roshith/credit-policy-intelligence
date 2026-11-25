"""Stage local policy sources and compare exact passages before publication."""
from collections import Counter
from datetime import date
from pathlib import Path
import re
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from ..config import BASE_DIR, RULE_MAX_FILE_BYTES
from ..database import shared_policy_connection
from .policy_ingestion import parse_document


def passage_changes(previous, current):
    def diff(left, right):
        remaining = Counter(p['checksum'] for p in left) - Counter(p['checksum'] for p in right)
        count = sum(remaining.values())
        examples = []
        for passage in left:
            key = passage['checksum']
            if remaining[key] and len(examples) < 12:
                examples.append({k: passage.get(k) for k in ('clause_number', 'page_number', 'section_heading', 'source_excerpt')})
                remaining[key] -= 1
        return count, examples

    added, additions = diff(current, previous)
    removed, removals = diff(previous, current)
    return {'added': added, 'removed': removed, 'unchanged': len(current) - added,
            'added_examples': additions, 'removed_examples': removals}


def published_rule_changes(previous, current):
    """Compare published requirements by wording and structured content across versions."""
    import json

    def entries(record):
        rows = {}
        for row in record['rules']:
            if row['status'] != 'APPROVED':
                continue
            rule = row['extracted']
            content = {key: rule[key] for key in ('rule_kind', 'products', 'customer_segments',
                       'geographies', 'metrics', 'thresholds', 'conditions', 'approvals', 'evidence_requirements', 'taxonomy_ids')}
            key = (' '.join(rule['source_quote'].split()), json.dumps(content, sort_keys=True))
            rows.setdefault(key, []).append({'id': row['id'], 'name': rule['name'], 'quote': key[0]})
        return rows

    old, new = entries(previous), entries(current)

    def changed(left, right):
        return [row for key, rows in left.items() for row in rows[len(right.get(key, ())):]]

    added, removed = changed(new, old), changed(old, new)
    return {'added': len(added), 'removed': len(removed), 'unchanged': sum(map(len, new.values())) - len(added),
            'added_examples': added[:8], 'removed_examples': removed[:8]}


def stage_policy_upload(file, *, owner, policy_id, code, title, version, effective_date):
    from hashlib import sha256
    from zipfile import BadZipFile
    from xml.etree.ElementTree import ParseError
    from pypdf.errors import PdfReadError
    from ..risk_knowledge.competency_projection import effective_start

    original = Path(file.filename or '').name
    suffix = Path(original).suffix.lower()
    if suffix not in ('.pdf', '.docx', '.txt', '.text'):
        raise HTTPException(422, 'Upload a PDF, DOCX, or UTF-8 text policy')
    data = file.file.read(RULE_MAX_FILE_BYTES + 1)
    if not 0 < len(data) <= RULE_MAX_FILE_BYTES:
        raise HTTPException(422, 'Policy file is empty or exceeds the upload limit')
    version, code, title = version.strip(), code.strip(), title.strip()
    if not version or (not policy_id and (not code or not title)):
        raise HTTPException(422, 'Enter a version and, for a new policy, a code and title')
    identifier = str(uuid4())
    directory = BASE_DIR / 'inventory_sources' / 'policy_uploads'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (identifier + suffix)
    try:
        path.write_bytes(data)
        try:
            spans = parse_document(path)
        except (ValueError, OSError, PdfReadError, BadZipFile, ParseError, KeyError, AttributeError) as error:
            raise HTTPException(422, 'The policy could not be read. Check that it contains selectable text') from error
        stated, _ = effective_start({'source_clauses': [{**c, 'id': c['sequence']} for c in spans]})
        if stated and stated != effective_date.isoformat():
            raise HTTPException(422, 'The effective date differs from the date on the policy cover')
        cover = '\n'.join(p['source_excerpt'] for p in spans[:4])
        declared_version = re.search(r'(?im)^\s*(?:policy )?version\s*[:=]\s*([^\n|]+)', cover)
        if declared_version and declared_version[1].strip() != version:
            raise HTTPException(422, 'The version differs from the version stated on the policy cover')
        checksum = sha256(data).hexdigest()
        with shared_policy_connection() as connection:
            previous = connection.execute('SELECT * FROM policy_documents WHERE policy_id=%s', (policy_id,)).fetchone() if policy_id else None
            if policy_id and not previous:
                raise HTTPException(404, 'Policy to revise was not found')
            if previous and connection.execute('SELECT 1 FROM policy_versions WHERE policy_id=%s AND version=%s', (policy_id, version)).fetchone():
                raise HTTPException(409, 'Choose a new policy version')
            if previous and previous['version'] == version:
                raise HTTPException(409, 'Choose a new policy version')
            if not previous and connection.execute('SELECT 1 FROM policy_documents WHERE policy_code=%s', (code,)).fetchone():
                raise HTTPException(409, 'That policy code is already registered. Select it as a revision')
            clauses = connection.execute('''SELECT cl.* FROM policy_clauses cl JOIN policy_versions v
                ON v.id=cl.policy_version_id WHERE v.policy_id=%s AND v.is_current ORDER BY cl.sequence''', (policy_id,)).fetchall() if previous else []
            changes = passage_changes(clauses, spans)
            payload = {'kind': 'staged_policy_upload', 'policy_id': policy_id, 'policy_code': previous['policy_code'] if previous else code,
                       'title': previous['title'] if previous else title, 'original_file_name': original,
                       'version': version, 'previous_version': previous['version'] if previous else None,
                       'effective_date': effective_date.isoformat(),
                       'page_count': max((p['page_number'] or 1 for p in spans)),
                       'file_name': path.name, 'checksum': checksum,
                       'synthetic': any('synthetic demonstration' in p['source_excerpt'].casefold()
                                        or 'synthetic policy data' in p['source_excerpt'].casefold() for p in spans),
                       'previous_source_available': bool(clauses), 'changes': changes}
            connection.execute("""INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload)
                VALUES ('metadata',%s,%s,%s)""", (owner, identifier, Jsonb(payload)))
        return {'upload_id': identifier, **{k: payload[k] for k in (
            'policy_id', 'policy_code', 'title', 'original_file_name', 'version', 'previous_version',
            'effective_date', 'previous_source_available', 'changes')}}
    except Exception:
        path.unlink(missing_ok=True)
        raise


def activate_staged_policy(connection, identifier, owner):
    """Register one staged file inside the same transaction that queues extraction."""
    row = connection.execute("""SELECT payload FROM risk_knowledge_objects
        WHERE kind='metadata' AND owner_id=%s AND id=%s AND payload->>'kind'='staged_policy_upload'
        FOR UPDATE""", (owner, identifier)).fetchone()
    if not row:
        raise HTTPException(404, 'Staged upload was not found')
    upload = row['payload']
    if upload.get('job_id'):
        job = connection.execute('SELECT * FROM rule_inventory_jobs WHERE id=%s', (upload['job_id'],)).fetchone()
        if job:
            return upload, job
    path = BASE_DIR / 'inventory_sources' / 'policy_uploads' / upload['file_name']
    from hashlib import sha256
    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != upload['checksum']:
        raise HTTPException(409, 'Staged source is unavailable. Upload the policy again')
    prior = None
    if upload['policy_id']:
        prior = connection.execute('SELECT * FROM policy_documents WHERE policy_id=%s FOR UPDATE', (upload['policy_id'],)).fetchone()
        if not prior or prior['version'] != upload['previous_version']:
            raise HTTPException(409, 'This policy changed after upload. Upload again to compare against the latest version')
    effective = date.fromisoformat(upload['effective_date'])
    values = (upload['version'], effective, upload['file_name'], str(path), path.suffix[1:].upper(), upload['page_count'])
    if prior:
        connection.execute("""UPDATE policy_documents SET version=%s,effective_date=%s,file_name=%s,
            local_pdf_path=%s,document_format=%s,page_count=%s WHERE policy_id=%s""", (*values, upload['policy_id']))
    else:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('policy-local-registration'))")
        sequence = connection.execute('SELECT COALESCE(MAX(display_order),0)+1 AS n FROM policy_documents').fetchone()['n']
        record = connection.execute("""INSERT INTO policy_documents(policy_code,title,policy_category,parent_policy,clause_number,display_order,
            source_type,policy_type,library_policy_id,status,summary,mistral_document_id,mistral_library_id,mistral_agent_id,
            version,effective_date,file_name,local_pdf_path,document_format,page_count)
            VALUES (%s,%s,'Uploaded policies','Uploaded policies','',%s,%s,'Uploaded policies',%s,'Active',%s,%s,
            'local-registration','not-provisioned',%s,%s,%s,%s,%s,%s)
            ON CONFLICT(policy_code) DO NOTHING RETURNING policy_id""",
            (upload['policy_code'], upload['title'], sequence, 'manufactured' if upload['synthetic'] else 'imported',
             f'UP-{sequence}', 'Uploaded policy source. Open Policy Evidence for its extracted clauses.',
             'local-upload:' + identifier, *values)).fetchone()
        if not record:
            raise HTTPException(409, 'That policy code was registered after upload')
        upload['policy_id'] = record['policy_id']
    return upload, None
