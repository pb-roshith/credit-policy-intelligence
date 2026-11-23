"""Small, idempotent schema upgrades for existing local databases.

``Base.metadata.create_all`` creates missing tables, but it does not add newly
introduced columns to tables that already exist. These upgrades keep older
development databases usable without deleting their data.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


logger = logging.getLogger(__name__)

_AUDIT_TABLES = (
    "audit_logs",
    "password_audit_events",
    "audit_entries",
    "library_sync_logs",
)


def prepare_database_schemas(engine: Engine) -> list[str]:
    """Create the PostgreSQL audit schema and move legacy public log tables."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL is the only supported database.")

    applied: list[str] = []
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS audit"))
        for table_name in _AUDIT_TABLES:
            location = connection.execute(
                text(
                    "SELECT table_schema FROM information_schema.tables "
                    "WHERE table_name = :table_name "
                    "AND table_schema IN ('public', 'audit') "
                    "ORDER BY CASE table_schema WHEN 'audit' THEN 0 ELSE 1 END"
                ),
                {"table_name": table_name},
            ).scalar()
            if location != "public":
                continue
            quoted_table = engine.dialect.identifier_preparer.quote(table_name)
            connection.execute(
                text(f"ALTER TABLE public.{quoted_table} SET SCHEMA audit")
            )
            applied.append(f"{table_name}->audit")

    if applied:
        logger.info("[startup] Moved log tables to audit schema: %s", ", ".join(applied))
    return applied


_ADDITIVE_MIGRATIONS: dict[str, dict[str, str]] = {
    "users": {
        "credential_version": "INTEGER NOT NULL DEFAULT 1",
        "identity_source": "VARCHAR(128)",
        # Existing accounts predate the approval workflow and remain usable.
        "is_approved": "BOOLEAN NOT NULL DEFAULT TRUE",
        "approved_at": "TIMESTAMP WITH TIME ZONE",
        "approved_by": "VARCHAR(64)",
        "failed_login_attempts": "INTEGER NOT NULL DEFAULT 0",
        "is_locked": "BOOLEAN NOT NULL DEFAULT FALSE",
        "locked_at": "TIMESTAMP WITH TIME ZONE",
    },
    "audit_logs": {
        "error_code": "VARCHAR(32)",
    },
    "deals": {
        "intake": "JSON",
        "creation_request_id": "VARCHAR(64)",
        "owner_user_id": "VARCHAR(36)",
        "library_sync_status": "VARCHAR(32) NOT NULL DEFAULT 'not_started'",
        "company_mistral_library_id": "VARCHAR(128)",
        "company_document_count": "INTEGER NOT NULL DEFAULT 0",
        "theme_palette": (
            """VARCHAR(256) NOT NULL DEFAULT '["#002060", "#800020"]'"""
        ),
    },
    "sections": {
        "orchestration_strategy": "TEXT",
        "original_generated_content": "TEXT",
        "final_generated_content": "TEXT",
        "moderation_status": "VARCHAR(16)",
        "moderation_details": "TEXT",
        "observability_details": "TEXT",
        "source_urls": "TEXT NOT NULL DEFAULT '[]'",
        "url_scrape_details": "TEXT",
        "edit_lock_user_id": "VARCHAR(36)",
        "edit_lock_user_name": "VARCHAR(64)",
        "edit_lock_expires_at": "TIMESTAMP WITH TIME ZONE",
    },
    "narrative_versions": {
        "is_final": "BOOLEAN NOT NULL DEFAULT FALSE",
    },
    "versions": {
        "review_comments": "TEXT",
        "reviewed_by": "VARCHAR(64)",
        "reviewed_at": "TIMESTAMP WITH TIME ZONE",
        "snapshot_json": "TEXT",
    },
}


def apply_additive_migrations(engine: Engine) -> list[str]:
    """Add known missing columns and return the migrations that were applied."""
    inspector = inspect(engine)
    if engine.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL is the only supported database.")
    audit_schema = "audit"
    existing_tables = set(inspector.get_table_names())
    audit_tables = set(inspector.get_table_names(schema=audit_schema))
    applied: list[str] = []

    with engine.begin() as connection:
        if "users" in existing_tables and engine.dialect.name == "postgresql":
            role_column = next(
                (
                    column
                    for column in inspector.get_columns("users")
                    if column["name"] == "role"
                ),
                None,
            )
            if role_column is not None and getattr(role_column["type"], "length", 0) < 32:
                connection.execute(text("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(32)"))
                applied.append("users.role_length")

        for table_name, columns in _ADDITIVE_MIGRATIONS.items():
            table_schema = audit_schema if table_name == "audit_logs" else None
            available_tables = audit_tables if table_schema else existing_tables
            if table_name not in available_tables:
                continue

            existing_columns = {
                column["name"]
                for column in inspector.get_columns(table_name, schema=table_schema)
            }
            quoted_table = engine.dialect.identifier_preparer.quote(table_name)
            qualified_table = (
                f"{table_schema}.{quoted_table}" if table_schema else quoted_table
            )

            for column_name, definition in columns.items():
                if column_name in existing_columns:
                    continue

                quoted_column = engine.dialect.identifier_preparer.quote(column_name)
                connection.execute(
                    text(
                        f"ALTER TABLE {qualified_table} "
                        f"ADD COLUMN {quoted_column} {definition}"
                    )
                )
                applied.append(f"{table_name}.{column_name}")

        if "users" in existing_tables:
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_user_id_lower ON users (LOWER(user_id))"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_identity_source ON users (identity_source) WHERE identity_source IS NOT NULL"))

        if "deals" in existing_tables:
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_deals_creation_request "
                "ON deals (owner_user_id, creation_request_id) WHERE creation_request_id IS NOT NULL"
            ))

        if "auth_sessions" in existing_tables:
            unique_user_id = any(
                constraint.get("column_names") == ["user_id"]
                for constraint in inspector.get_unique_constraints("auth_sessions")
            ) or any(
                index.get("unique") and index.get("column_names") == ["user_id"]
                for index in inspector.get_indexes("auth_sessions")
            )
            if not unique_user_id:
                quoted_sessions = engine.dialect.identifier_preparer.quote(
                    "auth_sessions"
                )
                quoted_index = engine.dialect.identifier_preparer.quote(
                    "uq_auth_sessions_user_id"
                )
                rows = connection.execute(
                    text(
                        f"SELECT id, user_id FROM {quoted_sessions} "
                        "ORDER BY created_at DESC, id DESC"
                    )
                ).mappings().all()
                retained_users: set[str] = set()
                for row in rows:
                    if row["user_id"] in retained_users:
                        connection.execute(
                            text(f"DELETE FROM {quoted_sessions} WHERE id = :id"),
                            {"id": row["id"]},
                        )
                    else:
                        retained_users.add(row["user_id"])
                connection.execute(
                    text(
                        f"CREATE UNIQUE INDEX {quoted_index} "
                        f"ON {quoted_sessions} (user_id)"
                    )
                )
                applied.append("auth_sessions.user_id_unique")

    if applied:
        logger.info("[startup] Applied database migrations: %s", ", ".join(applied))

    return applied


def backfill_deal_owners(engine: Engine, fallback_user_id: str) -> int:
    """Assign legacy unowned deals to one existing user before isolation applies."""
    with engine.begin() as connection:
        result = connection.execute(
            text(
                "UPDATE deals SET owner_user_id = :user_id "
                "WHERE owner_user_id IS NULL OR owner_user_id = ''"
            ),
            {"user_id": fallback_user_id},
        )
        return result.rowcount or 0
