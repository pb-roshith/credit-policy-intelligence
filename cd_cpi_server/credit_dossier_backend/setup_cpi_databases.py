"""Provision isolated CPI databases using the existing local credentials."""

from pathlib import Path
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.local_secrets import load_secrets, store_secrets


def main():
    secrets = load_secrets("backend")
    url = make_url(secrets["DATABASE_URL"])
    target = "cpi_credit_dossier_backend"
    with psycopg.connect(
        host=url.host, port=url.port or 5432, user=url.username,
        password=url.password, dbname="postgres", autocommit=True,
    ) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
    store_secrets("backend", {"DATABASE_URL": url.set(database=target).render_as_string(hide_password=False)})

    from app.database import Base, SessionLocal, engine
    from app import models  # noqa: F401
    from app.migrations import prepare_database_schemas, apply_additive_migrations
    from app.auth import seed_initial_users

    assert engine.url.database == target
    prepare_database_schemas(engine)
    Base.metadata.create_all(bind=engine)
    apply_additive_migrations(engine)
    with SessionLocal() as db:
        seed_initial_users(db)
    with engine.connect() as conn:
        from sqlalchemy import text
        print("Backend database:", conn.execute(text("SELECT current_database()")).scalar())
        print("Backend deals:", conn.execute(text("SELECT count(*) FROM deals")).scalar())
        print("Backend users:", conn.execute(text("SELECT count(*) FROM users")).scalar())

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "credit_dossier_mcp"))
    import database as mcp_database

    assert mcp_database.settings.postgres_database == "cpi_credit_dossier_mcp"
    mcp_database.init_db()
    with mcp_database.connection() as conn:
        print("MCP database:", conn.execute("SELECT current_database()").fetchone()["current_database"])
        print("MCP companies:", conn.execute("SELECT count(*) AS count FROM mcp_companies").fetchone()["count"])


if __name__ == "__main__":
    main()
