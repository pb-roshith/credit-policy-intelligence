"""
PostgreSQL SQLAlchemy engine, session factory and declarative Base.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


AUDIT_SCHEMA = "audit"


def audit_table_args() -> dict[str, str]:
    return {"schema": AUDIT_SCHEMA}


# ── Engine configuration ────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,  # Disabled to prevent massive SQL query logs in the terminal
    pool_pre_ping=True,
)

@event.listens_for(engine, "connect")
def _set_postgresql_lock_timeout(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute(f"SET lock_timeout = '{settings.DB_LOCK_TIMEOUT_SECONDS}s'")
    cursor.close()


# ── Session factory ─────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Declarative base ───────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency for FastAPI routes ───────────────────────────────
def get_db():
    """Yield a database session, rolling back failures and always closing it."""
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError:
        db.rollback()
        raise
    except Exception:
        # Non-database failures can still leave an open transaction behind.
        db.rollback()
        raise
    finally:
        db.close()
