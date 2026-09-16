"""Exercise migration and rollback in a disposable database, never live data."""
import unittest
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from app import database, user_store


class UserStoreMigrationTest(unittest.TestCase):
    def test_colliding_ids_preserved_and_unknown_owner_rolls_back(self):
        name = 'test_user_migration_' + uuid4().hex
        url = make_conninfo(database.DATABASE_URL, dbname=name)
        with psycopg.connect(database.DATABASE_URL, autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            with patch.object(database, 'DATABASE_URL', url), patch.object(user_store, 'DATABASE_URL', url):
                database.init_auth_db()
                database.init_credit_request_db()
                for owner in ('migration-a', 'migration-b'):
                    with psycopg.connect(url) as c:
                        c.execute("INSERT INTO public.users (user_id,password_hash,role,questions,created_at) VALUES (%s,'test','relationship_manager','[]',now())", (owner,))
                    legacy = 'user_' + sha256(owner.encode()).hexdigest()[:56]
                    token = database.data_schema.set(legacy)
                    try:
                        database.init_credit_request_db()
                        with database.db_connection() as c:
                            c.execute("INSERT INTO borrower (borrower_name) VALUES ('Same borrower')")
                            c.execute("""INSERT INTO credit_requests
                                (credit_request_number,borrower_id,borrower_name,industry,exposure,facility,rating,requested_amount,status,compliance_score)
                                VALUES ('CR-1',1,'Same borrower','Test',100,'Loan','A',100,'In Review',50)""")
                            c.execute("""INSERT INTO credit_request_policy_evaluations
                                (credit_request_number,clause_code,clause_name,result)
                                VALUES ('CR-1','TEST','Test clause','PASS')""")
                    finally:
                        database.data_schema.reset(token)
                unknown = 'user_' + 'f' * 56
                with psycopg.connect(url) as c:
                    c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(unknown)))
                with self.assertRaisesRegex(RuntimeError, 'Cannot establish ownership'):
                    user_store.migrate_user_store()
                with psycopg.connect(url) as c:
                    self.assertIsNone(c.execute("SELECT to_regnamespace('user')").fetchone()[0])
                    c.execute(sql.SQL('DROP SCHEMA {}').format(sql.Identifier(unknown)))
                user_store.migrate_user_store()
                user_store.migrate_user_store()
                with psycopg.connect(url) as c:
                    self.assertEqual(c.execute('SELECT user_id,borrower_id,credit_request_number FROM "user".credit_requests ORDER BY user_id').fetchall(),
                                     [('migration-a', 1, 'CR-1'), ('migration-b', 1, 'CR-1')])
                    self.assertEqual(c.execute('SELECT count(*) FROM "user".credit_request_policy_evaluations').fetchone()[0], 2)
                    self.assertEqual(c.execute("SELECT count(*) FROM pg_namespace WHERE nspname ~ '^user_[0-9a-f]{56}$'").fetchone()[0], 0)
        finally:
            with psycopg.connect(database.DATABASE_URL, autocommit=True) as admin:
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
