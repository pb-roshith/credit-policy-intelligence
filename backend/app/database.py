from contextvars import ContextVar

from fastapi import HTTPException
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import DATABASE_URL
from .bootstrap import initialize_database


account_user_id = ContextVar("account_user_id", default=None)


def db_connection():
    connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
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
    connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        connection.execute("SET LOCAL search_path TO credit_data")
    except BaseException:
        connection.close()
        raise
    return connection


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
