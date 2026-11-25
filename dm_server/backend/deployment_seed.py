"""Create and restore static PostgreSQL snapshots for the three deployed services."""

import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from psycopg.pq import Conninfo


DM_BACKEND = Path(__file__).resolve().parent
SEED_TABLE_DIR = DM_BACKEND / 'seed_table'
SEED_OTHERS_DIR = DM_BACKEND / 'seed_others'
DATABASES = {'cpi': 'CPI_SEED_DATABASE_URL', 'dossier': 'DOSSIER_SEED_DATABASE_URL',
             'mcp': 'MCP_SEED_DATABASE_URL'}
CATALOGS = {'cpi': 'credit_data.policy_documents', 'dossier': 'public.deals',
            'mcp': 'public.mcp_companies'}


def seed_url(database):
    key = DATABASES[database]
    configured = os.getenv(key)
    if configured is None:
        configured = dotenv_values(DM_BACKEND / '.env', interpolate=False).get(key)
    return (configured or '').strip()


def relocated_seed_path(path, root=SEED_OTHERS_DIR):
    path = Path(path)
    old_root = DM_BACKEND.parent / 'seed_others'
    if path.is_relative_to(old_root):
        return root / path.relative_to(old_root)
    return path


def postgres_command(tool, dsn, *args):
    binary = shutil.which(tool)
    if not binary:
        raise RuntimeError(f'{tool} is required on PATH')
    # Pass credentials only through the child process environment.
    environment = os.environ.copy()
    environment.pop('PGPASSWORD', None)
    for option in Conninfo.parse(dsn.encode('utf-8')):
        if option.val is None:
            continue
        if option.envvar is None:
            raise ValueError(f'Database connection option cannot be passed through the environment: {option.keyword.decode()}')
        environment[option.envvar.decode()] = option.val.decode('utf-8')
    environment['PGCLIENTENCODING'] = 'UTF8'
    return [binary, '--no-password', *map(str, args)], environment


def checksum(path):
    with path.open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def snapshot(database, dsn, directory):
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / f'{database}.dump'
    temporary = directory / f'{database}.{uuid4().hex}.tmp'
    try:
        command, env = postgres_command('pg_dump', dsn, '--format=custom', '--exclude-table=public.deployment_seed_snapshot', '--file', temporary)
        subprocess.run(command, env=env, check=True)
        subprocess.run(['pg_restore', '--list', str(temporary)], stdout=subprocess.DEVNULL, check=True)
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Saved {archive.name} ({archive.stat().st_size:,} bytes, SHA-256 {checksum(archive)})', flush=True)


def bundled_file(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f'Missing or invalid seed file: {name}')
    return path


def mcp_assets(root):
    folder = root / 'dossier_documents'
    entries = json.loads((folder / 'assets.json').read_text(encoding='utf-8'))
    paths = {}
    for entry in entries:
        path = bundled_file(folder, entry['file'])
        if checksum(path) != entry['sha256']:
            raise ValueError(f'Dossier document checksum mismatch: {entry["id"]}')
        paths[entry['id']] = path
    return paths


EMPTY_DATABASE = """SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_%'
    AND c.relkind IN ('r','p','v','m','S') LIMIT 1"""


def require_empty(query, message):
    return sql.SQL("DO $$ BEGIN IF EXISTS ({}) THEN RAISE EXCEPTION {}; END IF; END $$;\n").format(
        sql.SQL(query), sql.Literal(message)).as_string()


def binding_sql(database, root, assets):
    if database == 'dossier':
        return ''
    statements = ['CREATE TEMP TABLE seed_files (kind text, key text, path text, PRIMARY KEY (kind,key));']
    if database == 'mcp':
        files = [('mcp', str(key), path) for key, path in assets.items()]
        update = """
        UPDATE public.mcp_documents d SET local_path=f.path FROM seed_files f WHERE d.id::text=f.key;
        """
        validation = """SELECT 1 FROM public.mcp_documents d FULL JOIN seed_files f ON d.id::text=f.key
            WHERE d.id IS NULL OR f.key IS NULL"""
    else:
        files = []
        for directory in ('generated_policies', 'policy_docs', 'inventory_sources'):
            folder = root / directory
            if not folder.is_dir():
                raise ValueError(f'Missing seed folder: {folder}')
            if directory == 'inventory_sources':
                for path in folder.glob('*'):
                    if path.is_file() and len(path.stem) == 64:
                        if checksum(path) != path.stem:
                            raise ValueError(f'CPI evidence checksum mismatch: {path.name}')
                        files.append(('evidence', path.name, bundled_file(folder, path.name)))
                for path in (folder / 'policy_uploads').glob('*'):
                    if path.is_file():
                        files.append(('catalog', path.name, bundled_file(folder / 'policy_uploads', path.name)))
            else:
                files.extend(('catalog', path.name, bundled_file(folder, path.name)) for path in folder.iterdir() if path.is_file())
        workbook = bundled_file(root, 'risk_schema/Risk Data Model_Oct 2026.xlsx')
        files.append(('schema', workbook.name, workbook))
        evidence_key = "d.checksum || substring(lower(d.file_name) from '[.][^.]+$')"
        validation = f"""SELECT 1 FROM credit_data.policy_documents d LEFT JOIN seed_files f ON f.kind='catalog' AND f.key=d.file_name
            WHERE f.key IS NULL UNION ALL
            SELECT 1 FROM credit_data.inventory_documents d LEFT JOIN seed_files f ON f.kind='evidence' AND f.key={evidence_key}
            WHERE d.source_path IS NOT NULL AND f.key IS NULL"""
        update = f"""
        UPDATE credit_data.policy_documents d SET local_pdf_path=f.path FROM seed_files f WHERE f.kind='catalog' AND f.key=d.file_name;
        UPDATE credit_data.inventory_documents d SET source_path=f.path FROM seed_files f WHERE f.kind='evidence' AND f.key={evidence_key};
        UPDATE credit_data.risk_knowledge_objects d SET payload=jsonb_set(d.payload, '{{metadata,registered_path}}', to_jsonb(f.path))
            FROM seed_files f WHERE f.kind='schema' AND d.kind='documents' AND d.payload->>'document_type'='schema'
            AND d.payload->>'document_name'=f.key;
        """
    for kind, key, path in files:
        statements.append(sql.SQL('INSERT INTO seed_files VALUES ({},{},{});').format(
            sql.Literal(kind), sql.Literal(key), sql.Literal(str(path))).as_string())
    return '\n'.join([*statements, require_empty(validation, 'Snapshot document references do not match the seed files'), update])


def preflight(database, dsn, archive, *, startup=False):
    if not archive.is_file():
        raise ValueError(f'Missing database snapshot: {archive}')
    digest = checksum(archive)
    with psycopg.connect(dsn) as connection:
        if connection.execute("SELECT to_regclass('public.deployment_seed_snapshot')").fetchone()[0]:
            marker = connection.execute('SELECT sha256 FROM public.deployment_seed_snapshot WHERE service=%s', (database,)).fetchone()
            if marker == (digest,):
                return False
        if connection.execute(EMPTY_DATABASE).fetchone():
            if startup and connection.execute('SELECT to_regclass(%s)', (CATALOGS[database],)).fetchone()[0]:
                return False
            raise ValueError(f'{database} restore target must be an empty database')
        if database == 'cpi' and not connection.execute("SELECT 1 FROM pg_roles WHERE rolname='credit_user_runtime'").fetchone():
            raise ValueError('Create the credit_user_runtime role on the PostgreSQL server before restoring CPI')
    return True


def restore(database, dsn, archive, root, assets):
    mappings = binding_sql(database, root, assets)
    guard = "SELECT pg_advisory_xact_lock(hashtext('deployment_seed_snapshot'));\n"
    guard += require_empty(EMPTY_DATABASE, 'Seed restore target must be empty')
    marker = sql.SQL("""
        CREATE TABLE public.deployment_seed_snapshot (
            service text PRIMARY KEY, sha256 text NOT NULL, restored_at timestamptz NOT NULL DEFAULT now());
        INSERT INTO public.deployment_seed_snapshot(service,sha256) VALUES ({},{});\n
    """).format(sql.Literal(database), sql.Literal(checksum(archive))).as_string()
    command, env = postgres_command('psql', dsn, '-X', '--quiet', '--single-transaction',
                                    '--set', 'ON_ERROR_STOP=1', '--file=-')
    # Stream the archive SQL and file bindings into one transaction per database.
    with subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL) as target:
        with subprocess.Popen(['pg_restore', '--no-owner', '--no-privileges', '--file=-', str(archive)],
                              stdout=subprocess.PIPE) as source:
            try:
                target.stdin.write(guard.encode('utf-8'))
                shutil.copyfileobj(source.stdout, target.stdin)
                if source.wait() != 0:
                    target.terminate()
                    raise RuntimeError(f'Could not read {archive.name}')
                target.stdin.write(('\n' + mappings + marker).encode('utf-8'))
                target.stdin.close()
            except BrokenPipeError as error:
                source.terminate()
                raise RuntimeError(f'{database} restore rejected by PostgreSQL') from error
        if target.wait() != 0:
            raise RuntimeError(f'{database} restore failed')
    print(f'Restored {database}', file=sys.stderr, flush=True)


def restore_gemini_store(root, destination):
    source = bundled_file(root, 'gemini.sqlite3')
    destination = destination.resolve()
    if destination == source:
        raise ValueError('Set GEMINI_STORE_PATH to a writable runtime copy outside the static seed')
    if destination.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f'{destination.name}.{uuid4().hex}.tmp')
    try:
        shutil.copyfile(source, temporary)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            return
    finally:
        temporary.unlink(missing_ok=True)
    print('Initialized the Gemini store', file=sys.stderr, flush=True)


def restore_on_startup(database, *, gemini=False, prepare=None):
    dsn = seed_url(database)
    if not dsn:
        return False
    archive = SEED_TABLE_DIR / f'{database}.dump'
    files = SEED_OTHERS_DIR
    # CPI and Data Manufacturing can start together against the same database.
    # Serialize the startup check and restore while psql uses its own transaction.
    with psycopg.connect(dsn) as lock:
        lock.execute("SELECT pg_advisory_xact_lock(hashtext('deployment_seed_startup'))")
        needs_restore = preflight(database, dsn, archive, startup=True)
        if needs_restore:
            assets = mcp_assets(files) if database == 'mcp' else {}
            restore(database, dsn, archive, files, assets)
        if prepare and (needs_restore or (
                lock.execute("SELECT to_regclass('public.deployment_seed_snapshot')").fetchone()[0]
                and lock.execute('SELECT 1 FROM public.deployment_seed_snapshot WHERE service=%s', (database,)).fetchone())):
            prepare(dsn)
            return True
        if gemini:
            store = Path(os.getenv('GEMINI_STORE_PATH') or DM_BACKEND.parents[1] / '.ai-data' / 'gemini.sqlite3')
            restore_gemini_store(files, store)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('snapshot', 'restore'))
    parser.add_argument('--database', choices=DATABASES, action='append')
    parser.add_argument('--tables', type=Path, default=SEED_TABLE_DIR)
    parser.add_argument('--files', type=Path, default=SEED_OTHERS_DIR)
    parser.add_argument('--gemini-store', type=Path, default=os.getenv('GEMINI_STORE_PATH'))
    args = parser.parse_args()
    targets = {}
    for database in dict.fromkeys(args.database or DATABASES):
        key = DATABASES[database]
        dsn = seed_url(database)
        if not dsn:
            parser.error(f'Set {key} to the database connection string')
        targets[database] = dsn
    if args.action == 'snapshot':
        for database, dsn in targets.items():
            snapshot(database, dsn, args.tables)
        return
    pending = {database: dsn for database, dsn in targets.items()
               if preflight(database, dsn, args.tables / f'{database}.dump')}
    assets = mcp_assets(args.files) if 'mcp' in pending else {}
    for database, dsn in pending.items():
        restore(database, dsn, args.tables / f'{database}.dump', args.files, assets)
    if 'mcp' in targets and args.gemini_store:
        restore_gemini_store(args.files, args.gemini_store)


if __name__ == '__main__':
    main()
