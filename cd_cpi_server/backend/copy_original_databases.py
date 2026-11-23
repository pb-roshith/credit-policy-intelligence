"""Copy read-only original database snapshots into isolated CPI databases.

Run without arguments to inspect, or with --copy to clone and verify all tables.
Existing CPI databases are retained under timestamped backup names.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

from dotenv import dotenv_values
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.local_secrets import load_secrets


BACKEND = Path(__file__).resolve().parent
CPI = BACKEND.parent
ORIGINAL = CPI.parent.parent / "Credit_Dossier"


def original_secrets(namespace):
    spec = importlib.util.spec_from_file_location(
        "original_secrets", ORIGINAL / "backend/app/local_secrets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_secrets(namespace)


def targets():
    source_url = make_url(original_secrets("backend")["DATABASE_URL"])
    target_url = make_url(load_secrets("backend")["DATABASE_URL"])
    backend = dict(host=source_url.host, port=source_url.port or 5432,
                   user=source_url.username, password=source_url.password)
    destination = dict(host=target_url.host, port=target_url.port or 5432,
                       user=target_url.username, password=target_url.password)
    source_mcp = dotenv_values(ORIGINAL / "mcp/.env")
    target_mcp = dotenv_values(CPI / "mcp/.env")
    def mcp_params(config, secret):
        return dict(host=config.get("POSTGRES_HOST", "127.0.0.1"),
                    port=int(config.get("POSTGRES_PORT", "5432")),
                    user=config.get("POSTGRES_USER", "postgres"),
                    password=secret.get("POSTGRES_PASSWORD") or config.get("POSTGRES_PASSWORD") or "root")
    return [
        ("backend", backend, source_url.database, destination, target_url.database),
        ("mcp", mcp_params(source_mcp, original_secrets("mcp")), source_mcp["POSTGRES_DB"],
         mcp_params(target_mcp, load_secrets("mcp")), target_mcp["POSTGRES_DB"]),
    ]


def tables(conn):
    return conn.execute("""SELECT schemaname, tablename FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schemaname, tablename""").fetchall()


def inventory(conn, digest=False):
    result = {}
    for schema, table in tables(conn):
        identifier = sql.Identifier(schema, table)
        count = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(identifier)).fetchone()[0]
        entry = {"rows": count}
        if digest:
            hashes = []
            with conn.cursor(name=f"verify_{len(result)}") as cursor:
                cursor.execute(sql.SQL("SELECT row_to_json(t)::text FROM {} AS t").format(identifier))
                for row in cursor:
                    hashes.append(hashlib.sha256(row[0].encode()).digest())
            entry["sha256"] = hashlib.sha256(b"".join(sorted(hashes))).hexdigest()
        result[f"{schema}.{table}"] = entry
    return result


def run_tool(tool, params, database, args):
    binary = shutil.which(tool)
    if not binary:
        raise RuntimeError(f"{tool} is unavailable")
    env = os.environ.copy()
    env["PGPASSWORD"] = params["password"] or ""
    command = [binary, "--host", params["host"], "--port", str(params["port"]),
               "--username", params["user"], "--dbname", database, *args]
    subprocess.run(command, env=env, check=True, capture_output=True, text=True)


def copy_local_files(conn):
    """Copy local documents and rewrite paths only in the staged CPI copy."""
    mappings = [(ORIGINAL / "backend", BACKEND), (ORIGINAL / "mcp", CPI / "mcp")]
    copied = 0
    missing = []
    for schema, table, column in conn.execute("""SELECT table_schema, table_name, column_name
        FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        AND column_name IN ('file_path', 'local_path', 'template_file_path')""").fetchall():
        table_id = sql.Identifier(schema, table)
        column_id = sql.Identifier(column)
        values = conn.execute(sql.SQL("SELECT DISTINCT {} FROM {} WHERE {} IS NOT NULL")
                              .format(column_id, table_id, column_id)).fetchall()
        for (value,) in values:
            if not value:
                continue
            source_path = Path(value)
            is_absolute = source_path.is_absolute()
            if not is_absolute:
                base = ORIGINAL / ("mcp" if column == "local_path" else "backend")
                source_path = base / source_path
            source_path = source_path.resolve()
            for source_base, destination_base in mappings:
                if source_path.is_relative_to(source_base):
                    relative = source_path.relative_to(source_base)
                    destination_path = destination_base / relative
                    break
            else:
                raise RuntimeError(f"Document is outside original project: {source_path}")
            if source_path.is_file():
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                if destination_path.exists() and source_path.read_bytes() != destination_path.read_bytes():
                    backup = destination_path.with_name(destination_path.name + ".before-copy")
                    if backup.exists():
                        raise RuntimeError(f"File backup already exists: {backup}")
                    shutil.copy2(destination_path, backup)
                shutil.copy2(source_path, destination_path)
                assert hashlib.sha256(source_path.read_bytes()).digest() == hashlib.sha256(destination_path.read_bytes()).digest()
                copied += 1
            else:
                missing.append(str(source_path))
            if is_absolute:
                conn.execute(sql.SQL("UPDATE {} SET {} = %s WHERE {} = %s")
                             .format(table_id, column_id, column_id), (str(destination_path), value))
    return {"files_copied": copied, "missing_source_files": sorted(set(missing))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--copy", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKEND / ".data" / "database_copies" / stamp
    report = {}
    staged = []
    for label, source, source_db, dest, target_db in targets():
        if not target_db.startswith("cpi_credit_dossier_") or source_db == target_db:
            raise RuntimeError("Refusing an unisolated destination")
        with psycopg.connect(**source, dbname=source_db) as original:
            original.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            source_data = inventory(original, digest=args.copy)
            print(label, "source:", source_db, "tables:", len(source_data),
                  "rows:", sum(x["rows"] for x in source_data.values()), flush=True)
            with psycopg.connect(**dest, dbname=target_db) as current:
                current.execute("SET TRANSACTION READ ONLY")
                current_data = inventory(current)
                print(label, "destination:", target_db, "rows:",
                      sum(x["rows"] for x in current_data.values()), flush=True)
            if not args.copy:
                print(json.dumps(source_data, indent=2), flush=True)
                continue
            backup_dir.mkdir(parents=True, exist_ok=True)
            snapshot = original.execute("SELECT pg_export_snapshot()").fetchone()[0]
            dump = backup_dir / f"{source_db}.dump"
            run_tool("pg_dump", source, source_db, ["--format=custom", "--snapshot", snapshot,
                     "--file", str(dump)])
            stage_db = f"{target_db}_copy_{stamp}"
            with psycopg.connect(**dest, dbname="postgres", autocommit=True) as admin:
                admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(stage_db)))
            run_tool("pg_restore", dest, stage_db, ["--exit-on-error", "--single-transaction", str(dump)])
            with psycopg.connect(**dest, dbname=stage_db) as copied:
                restored = inventory(copied, digest=True)
                if restored != source_data:
                    raise RuntimeError(f"{label} data verification failed")
                sequences = original.execute("SELECT schemaname, sequencename, last_value FROM pg_sequences ORDER BY 1, 2").fetchall()
                if copied.execute("SELECT schemaname, sequencename, last_value FROM pg_sequences ORDER BY 1, 2").fetchall() != sequences:
                    raise RuntimeError(f"{label} sequence verification failed")
                file_report = copy_local_files(copied)
            report[label] = dict(source=source_db, destination=target_db,
                                 verified_tables=source_data, files=file_report,
                                 previous_cpi_database=f"{target_db}_before_{stamp}")
            staged.append((dest, target_db, stage_db))
            print(label, "all table contents and sequences verified;", file_report, flush=True)
    # Switch only after both staged databases have passed verification.
    for dest, target_db, stage_db in staged:
        with psycopg.connect(**dest, dbname="postgres", autocommit=True) as admin:
            # Briefly disconnect CPI only, preventing new sessions during rename.
            admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(target_db)))
            try:
                admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (target_db,))
                with admin.transaction():
                    admin.execute(sql.SQL("ALTER DATABASE {} RENAME TO {}")
                                  .format(sql.Identifier(target_db), sql.Identifier(f"{target_db}_before_{stamp}")))
                    admin.execute(sql.SQL("ALTER DATABASE {} RENAME TO {}")
                                  .format(sql.Identifier(stage_db), sql.Identifier(target_db)))
            except Exception:
                admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(target_db)))
                raise
            admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true")
                          .format(sql.Identifier(f"{target_db}_before_{stamp}")))
        print("Activated:", target_db, flush=True)
    if args.copy:
        (backup_dir / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Verification report:", backup_dir / "verification.json", flush=True)


if __name__ == "__main__":
    main()
