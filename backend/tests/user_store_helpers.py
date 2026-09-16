import psycopg
from psycopg import sql
from app.config import DATABASE_URL


def delete_test_user(user_id):
    if not user_id.startswith(('dashboard-test-', 'isolation-test-')):
        raise ValueError('Only test accounts may be cleaned up')
    with psycopg.connect(DATABASE_URL) as c:
        c.execute('SET CONSTRAINTS ALL DEFERRED')
        tables = c.execute("SELECT table_name FROM information_schema.columns WHERE table_schema='user' AND column_name='user_id'").fetchall()
        for (table,) in tables:
            if table == 'latest_borrower_exposure':
                continue
            c.execute(sql.SQL('DELETE FROM "user".{} WHERE user_id=%s').format(sql.Identifier(table)), (user_id,))
