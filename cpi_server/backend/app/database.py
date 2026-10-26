from contextvars import ContextVar
from functools import wraps
import logging
import random
from time import sleep

from fastapi import HTTPException
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import (
    DATABASE_CONNECT_TIMEOUT_SECONDS, DATABASE_RETRY_BASE_DELAY_MS,
    DATABASE_STATEMENT_TIMEOUT_MS, DATABASE_TRANSACTION_RETRIES, DATABASE_URL,
)
from .bootstrap import initialize_database


account_user_id = ContextVar("account_user_id", default=None)
logger = logging.getLogger("credit_policy_intelligence.database")
TRANSIENT_TRANSACTION_ERRORS = (
    psycopg.errors.DeadlockDetected,
    psycopg.errors.SerializationFailure,
)


def _retry_delay(attempt: int) -> float:
    base = DATABASE_RETRY_BASE_DELAY_MS / 1000
    return base * (2 ** (attempt - 1)) + random.uniform(0, base)


def retry_on_db_conflict(function):
    """Retry a database-only unit after PostgreSQL rolls back a transient conflict."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        for attempt in range(1, DATABASE_TRANSACTION_RETRIES + 1):
            try:
                return function(*args, **kwargs)
            except TRANSIENT_TRANSACTION_ERRORS as error:
                if attempt == DATABASE_TRANSACTION_RETRIES:
                    logger.exception("Database transaction failed after %s attempts", attempt)
                    raise
                delay = _retry_delay(attempt)
                logger.warning(
                    "Retrying database transaction after %s (attempt %s/%s, %.0f ms)",
                    type(error).__name__, attempt + 1, DATABASE_TRANSACTION_RETRIES, delay * 1000,
                )
                sleep(delay)
    return wrapped


def run_db_transaction(operation, *, shared: bool = False):
    """Run and, when safe, replay one complete database transaction."""
    connection_factory = shared_policy_connection if shared else db_connection

    @retry_on_db_conflict
    def execute():
        with connection_factory() as connection:
            return operation(connection)

    return execute()


def db_connection():
    connection = _connect()
    try:
        owner = account_user_id.get()
        if owner is not None:
            if not owner or owner == "__legacy_unassigned__":
                raise HTTPException(status_code=403, detail="Account data access is unavailable")
            connection.execute(sql.SQL("SET LOCAL app.user_id TO {}").format(sql.Literal(owner)))
            connection.execute("SET LOCAL ROLE credit_user_runtime")
            connection.execute('SET LOCAL search_path TO "user"')
            return connection
        connection.execute("SET LOCAL search_path TO credit_data")
    except BaseException:
        connection.close()
        raise
    return connection


def shared_policy_connection():
    """Open the common Policy Intelligence store, independent of the signed-in user."""
    connection = _connect()
    try:
        connection.execute("SET LOCAL search_path TO credit_data")
    except BaseException:
        connection.close()
        raise
    return connection


def _connect():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        connect_timeout=DATABASE_CONNECT_TIMEOUT_SECONDS,
        options=f"-c statement_timeout={DATABASE_STATEMENT_TIMEOUT_MS} "
                f"-c idle_in_transaction_session_timeout={DATABASE_STATEMENT_TIMEOUT_MS}",
    )


def ensure_account_defaults():
    """Provision required defaults for the authenticated account."""
    with db_connection() as connection:
        connection.execute("""INSERT INTO approval_authority_rules
            (rule_order, maximum_post_approval_exposure, authority_name, authority_rank)
            VALUES (1,25000000,'Credit Officer',1), (2,75000000,'Senior Credit Officer',2),
            (3,150000000,'Credit Committee',3), (4,NULL,'Executive Committee',4)
            ON CONFLICT (user_id, rule_order) DO NOTHING""")


def resolve_borrower(connection, name: str, borrower_id: int | None = None) -> int:
    name = name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Borrower name must contain at least two characters")
    if borrower_id is not None:
        row = connection.execute(
            "SELECT borrower_id FROM borrower "
            "WHERE borrower_id = %s AND LOWER(BTRIM(borrower_name)) = LOWER(%s)",
            (borrower_id, name),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=422, detail="Borrower ID and name do not match")
        return row["borrower_id"]
    return connection.execute("""
        INSERT INTO borrower (borrower_name) VALUES (%s)
        ON CONFLICT (user_id, LOWER(BTRIM(borrower_name))) DO UPDATE
        SET borrower_name = borrower.borrower_name
        RETURNING borrower_id
    """, (name,)).fetchone()["borrower_id"]
