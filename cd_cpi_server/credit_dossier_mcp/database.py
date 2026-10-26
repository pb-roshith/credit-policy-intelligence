"""PostgreSQL persistence for the local credit-intelligence MCP."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from catalog import TABLE_COLUMNS, TABLE_NAMES
from settings import settings


@contextmanager
def connection(database: str | None = None) -> Iterator[psycopg.Connection]:
    with psycopg.connect(
        **settings.postgres_kwargs(database),
        row_factory=dict_row,
    ) as conn:
        yield conn


def ensure_database() -> None:
    """Create the configured local database when it does not exist."""
    with psycopg.connect(
        **settings.postgres_kwargs("postgres"),
        autocommit=True,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (settings.postgres_database,),
        ).fetchone()
        if not exists:
            conn.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(settings.postgres_database)
                )
            )


def init_db() -> None:
    """Create metadata tables and the 16 company-scoped credit tables."""
    ensure_database()
    with connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_companies (
                id BIGSERIAL PRIMARY KEY,
                owner_user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                industry TEXT NOT NULL,
                geography TEXT NOT NULL,
                segment TEXT NOT NULL DEFAULT 'Mid Corporate',
                kyc_status TEXT NOT NULL DEFAULT 'Verified',
                mistral_library_id TEXT,
                context JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute("ALTER TABLE mcp_companies ADD COLUMN IF NOT EXISTS owner_user_id TEXT NOT NULL DEFAULT 'admin'")
        conn.execute("ALTER TABLE mcp_companies DROP CONSTRAINT IF EXISTS mcp_companies_name_key")
        conn.execute("ALTER TABLE mcp_companies DROP CONSTRAINT IF EXISTS mcp_companies_normalized_name_key")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_company_owner_name ON mcp_companies (owner_user_id, normalized_name)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_documents (
                id BIGSERIAL PRIMARY KEY,
                company_id BIGINT NOT NULL
                    REFERENCES mcp_companies(id) ON DELETE CASCADE,
                document_number INTEGER NOT NULL,
                document_name TEXT NOT NULL,
                local_path TEXT,
                mistral_document_id TEXT,
                summary TEXT NOT NULL,
                processing_status TEXT NOT NULL DEFAULT 'local',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (company_id, document_name)
            )
            """
        )
        conn.execute("DROP TABLE IF EXISTS mcp_client_registry")
        conn.execute("DROP FUNCTION IF EXISTS sync_mcp_client_normalized_name()")
        conn.execute(
            """
            ALTER TABLE mcp_documents
            ADD COLUMN IF NOT EXISTS generator_version INTEGER NOT NULL DEFAULT 1
            """
        )
        conn.execute("CREATE SCHEMA IF NOT EXISTS credit_dossier")
        for table_name in TABLE_NAMES:
            schema_name, bare_name = table_name.split(".", 1)
            conn.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        id BIGSERIAL PRIMARY KEY,
                        company_id BIGINT NOT NULL
                            REFERENCES mcp_companies(id) ON DELETE CASCADE,
                        record_key TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        source_document TEXT,
                        manufactured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE (company_id, record_key)
                    )
                    """
                ).format(sql.Identifier(schema_name, bare_name))
            )
            for column_name in TABLE_COLUMNS[table_name]:
                conn.execute(
                    sql.SQL(
                        "ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} TEXT"
                    ).format(
                        sql.Identifier(schema_name, bare_name),
                        sql.Identifier(column_name),
                    )
                )
        conn.commit()


def normalize_company_name(value: str) -> str:
    return " ".join(value.lower().split())


def _text_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)
    return str(value)


def upsert_company(
    owner_user_id: str,
    name: str,
    industry: str,
    geography: str,
    context: dict[str, object],
) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO mcp_companies (
                owner_user_id, name, normalized_name, industry, geography, segment,
                kyc_status, context
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (owner_user_id, normalized_name) DO UPDATE SET
                name = EXCLUDED.name,
                industry = EXCLUDED.industry,
                geography = EXCLUDED.geography,
                segment = EXCLUDED.segment,
                kyc_status = EXCLUDED.kyc_status,
                context = EXCLUDED.context,
                updated_at = NOW()
            RETURNING *
            """,
            (
                owner_user_id,
                name,
                normalize_company_name(name),
                industry,
                geography,
                context.get("segment", "Mid Corporate"),
                context.get("kyc_status", "Verified"),
                Jsonb(context),
            ),
        ).fetchone()
        conn.commit()
        return dict(row)


def get_company(owner_user_id: str, name: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM mcp_companies
            WHERE owner_user_id = %s AND normalized_name = %s
            """,
            (owner_user_id, normalize_company_name(name)),
        ).fetchone()
        return dict(row) if row else None


def list_companies(owner_user_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT c.name, c.industry, c.geography, c.segment, c.kyc_status,
                   c.mistral_library_id,
                   COUNT(d.id)::INTEGER AS document_count
            FROM mcp_companies c
            LEFT JOIN mcp_documents d ON d.company_id = c.id
            WHERE c.owner_user_id = %s
            GROUP BY c.id
            ORDER BY c.name
            """,
            (owner_user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def update_company_library(company_id: int, library_id: str) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE mcp_companies
            SET mistral_library_id = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (library_id, company_id),
        )
        conn.commit()


def upsert_document(
    company_id: int,
    document_number: int,
    document_name: str,
    summary: str,
    local_path: Path | None,
    mistral_document_id: str | None,
    processing_status: str,
    generator_version: int = 2,
) -> None:
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO mcp_documents (
                company_id, document_number, document_name, local_path,
                mistral_document_id, summary, processing_status,
                generator_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (company_id, document_name) DO UPDATE SET
                document_number = EXCLUDED.document_number,
                local_path = EXCLUDED.local_path,
                mistral_document_id = COALESCE(
                    EXCLUDED.mistral_document_id,
                    mcp_documents.mistral_document_id
                ),
                summary = EXCLUDED.summary,
                processing_status = EXCLUDED.processing_status,
                generator_version = EXCLUDED.generator_version,
                updated_at = NOW()
            """,
            (
                company_id,
                document_number,
                document_name,
                str(local_path) if local_path else None,
                mistral_document_id,
                summary,
                processing_status,
                generator_version,
            ),
        )
        conn.commit()


def list_documents(owner_user_id: str, company_name: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT d.document_number, d.document_name, d.local_path,
                   d.mistral_document_id, d.summary, d.processing_status,
                   d.generator_version,
                   c.mistral_library_id
            FROM mcp_documents d
            JOIN mcp_companies c ON c.id = d.company_id
            WHERE c.owner_user_id = %s AND c.normalized_name = %s
            ORDER BY d.document_number
            """,
            (owner_user_id, normalize_company_name(company_name)),
        ).fetchall()
        return [dict(row) for row in rows]


def get_document(owner_user_id: str, company_name: str, document_name: str) -> dict | None:
    documents = list_documents(owner_user_id, company_name)
    return next(
        (doc for doc in documents if doc["document_name"] == document_name),
        None,
    )


def seed_credit_tables(
    company_id: int,
    rows_by_table: dict[str, list[dict[str, object]]],
    progress_callback: Callable[[str, int], None] | None = None,
) -> int:
    inserted = 0
    with connection() as conn:
        for table_name, rows in rows_by_table.items():
            if table_name not in TABLE_NAMES:
                raise ValueError(f"Unknown table: {table_name}")
            schema_name, bare_name = table_name.split(".", 1)
            qualified_table = sql.Identifier(schema_name, bare_name)
            conn.execute(
                sql.SQL("DELETE FROM {} WHERE company_id = %s").format(
                    qualified_table
                ),
                (company_id,),
            )
            business_columns = TABLE_COLUMNS[table_name]
            for index, payload in enumerate(rows, start=1):
                record_key = str(
                    payload.get("particular")
                    or payload.get("statement_year")
                    or payload.get("forecast_year")
                    or payload.get("facility_type")
                    or payload.get("owner_details")
                    or payload.get("covenant_type")
                    or payload.get("exception_code")
                    or payload.get("credit_committee_name")
                    or payload.get("transaction_date")
                    or payload.get("collateral_category")
                    or payload.get("exposure_type")
                    or payload.get("business_activities")
                    or index
                )
                business_values = [
                    _text_value(payload.get(column_name))
                    for column_name in business_columns
                ]
                insert_columns = (
                    "company_id",
                    "record_key",
                    "payload",
                    "source_document",
                    *business_columns,
                )
                update_assignments = [
                    sql.SQL("{} = EXCLUDED.{}").format(
                        sql.Identifier(column_name),
                        sql.Identifier(column_name),
                    )
                    for column_name in business_columns
                ]
                conn.execute(
                    sql.SQL(
                        """
                        INSERT INTO {} ({})
                        VALUES ({})
                        ON CONFLICT (company_id, record_key) DO UPDATE SET
                            payload = EXCLUDED.payload,
                            source_document = EXCLUDED.source_document,
                            {},
                            manufactured_at = NOW()
                        """
                    ).format(
                        qualified_table,
                        sql.SQL(", ").join(
                            sql.Identifier(column_name)
                            for column_name in insert_columns
                        ),
                        sql.SQL(", ").join(
                            sql.Placeholder() for _ in insert_columns
                        ),
                        sql.SQL(", ").join(update_assignments),
                    ),
                    (
                        company_id,
                        record_key,
                        Jsonb(payload),
                        "Synthetic manufactured credit data pack",
                        *business_values,
                    ),
                )
                inserted += 1
            if progress_callback:
                progress_callback(table_name, len(rows))
        conn.commit()
    return inserted


def describe_table(owner_user_id: str, company_name: str, table_name: str) -> dict:
    if table_name not in TABLE_NAMES:
        raise ValueError("Unknown credit intelligence table.")
    company = get_company(owner_user_id, company_name)
    if not company:
        raise ValueError(f'Company "{company_name}" is not configured.')
    schema_name, bare_name = table_name.split(".", 1)
    with connection() as conn:
        columns = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema_name, bare_name),
        ).fetchall()
        count = conn.execute(
            sql.SQL("SELECT COUNT(*) AS count FROM {} WHERE company_id = %s").format(
                sql.Identifier(schema_name, bare_name)
            ),
            (company["id"],),
        ).fetchone()["count"]
    return {
        "table": table_name,
        "columns": [row["column_name"] for row in columns],
        "rowCount": count,
    }


def fetch_table_rows(
    owner_user_id: str,
    company_name: str,
    table_name: str,
    limit: int = 20,
) -> list[dict]:
    if table_name not in TABLE_NAMES:
        raise ValueError("Unknown credit intelligence table.")
    company = get_company(owner_user_id, company_name)
    if not company:
        raise ValueError(f'Company "{company_name}" is not configured.')
    schema_name, bare_name = table_name.split(".", 1)
    safe_limit = max(1, min(limit, 100))
    with connection() as conn:
        rows = conn.execute(
            sql.SQL(
                """
                SELECT record_key, payload, source_document, manufactured_at
                FROM {}
                WHERE company_id = %s
                ORDER BY id
                LIMIT {}
                """
            ).format(
                sql.Identifier(schema_name, bare_name),
                sql.Literal(safe_limit),
            ),
            (company["id"],),
        ).fetchall()
    return [
        {
            "record_key": row["record_key"],
            **dict(row["payload"]),
            "source_document": row["source_document"],
            "manufactured_at": row["manufactured_at"].isoformat(),
        }
        for row in rows
    ]


def delete_company(owner_user_id: str, company_name: str) -> bool:
    with connection() as conn:
        result = conn.execute(
            "DELETE FROM mcp_companies WHERE owner_user_id = %s AND normalized_name = %s",
            (owner_user_id, normalize_company_name(company_name)),
        )
        conn.commit()
        return result.rowcount > 0
