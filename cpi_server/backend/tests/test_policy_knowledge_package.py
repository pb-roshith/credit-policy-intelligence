"""Package integrity and rollback-only PostgreSQL deployment tests."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from psycopg import sql
from app.services import policy_knowledge_package as package


class KnowledgePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.envelope = package.read_package()

    def test_bundled_package_contains_real_corpus_and_no_customer_tables(self):
        payload = self.envelope['payload']
        self.assertEqual(len(payload['records']), 35)
        self.assertEqual(set(payload['tables']), set(package.TABLES))
        self.assertGreater(package.summary(payload)['rules'], 0)
        self.assertNotIn('local_pdf_path', payload['tables']['policy_documents'][0])
        self.assertNotIn('mistral_document_id', payload['tables']['policy_documents'][0])

    def test_tampered_package_is_rejected(self):
        value = deepcopy(self.envelope)
        value['payload']['records'][0]['policy_name'] = 'Changed'
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'knowledge.json').write_text(package.encoded(value), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'package checksum'):
                package.read_package(directory)

    def test_incompatible_ontology_is_rejected(self):
        payload = deepcopy(self.envelope['payload'])
        payload['ontology_version'] = 'incompatible'
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            package.validate_package(payload)

    def test_changed_source_is_rejected(self):
        payload = deepcopy(self.envelope['payload'])
        first = next(iter(payload['sources']))
        payload['sources'][first] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source changed'):
            package.validate_package(payload)

    def test_changed_evidence_is_rejected(self):
        payload = deepcopy(self.envelope['payload'])
        payload['tables']['policy_clauses'][0]['source_excerpt'] += 'changed'
        with self.assertRaisesRegex(ValueError, 'Evidence passage'):
            package.validate_package(payload)

    def test_modified_review_state_without_resealing_is_rejected(self):
        payload = deepcopy(self.envelope['payload'])
        payload['records'][0]['rules'][0]['status'] = 'REJECTED'
        with self.assertRaisesRegex(ValueError, 'record checksum'):
            package.validate_package(payload)

    def test_path_traversal_is_rejected(self):
        for name in ('../secrets', 'C:\\secrets', '/etc/passwd', '..'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                package.local_source(name)

    def test_autoload_skips_populated_catalog(self):
        from unittest.mock import MagicMock
        db = MagicMock()
        db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {'exists': 1}
        with patch.object(package, 'shared_policy_connection', db), patch.object(package, 'import_package') as load:
            package.autoload_package()
            load.assert_not_called()

    def test_autoload_can_be_disabled(self):
        with patch.dict(os.environ, {'POLICY_KNOWLEDGE_AUTO_IMPORT': 'false'}), patch.object(package, 'import_package') as load:
            package.autoload_package()
            load.assert_not_called()

    def test_autoload_runs_for_empty_catalog(self):
        from unittest.mock import MagicMock
        db = MagicMock()
        db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
        with patch.dict(os.environ, {'POLICY_KNOWLEDGE_AUTO_IMPORT': 'true'}), patch.object(package, 'shared_policy_connection', db), patch.object(package, 'import_package') as load:
            package.autoload_package()
            load.assert_called_once_with()


@unittest.skipUnless(os.getenv('RUN_KNOWLEDGE_PACKAGE_DB_TESTS') == '1', 'Enable rollback-only PostgreSQL package test')
class KnowledgePackageDatabaseTests(unittest.TestCase):
    def setUp(self):
        from app.database import _connect
        self.connection = _connect()
        self.addCleanup(self.connection.close)
        self.addCleanup(self.connection.rollback)
        schema = 'knowledge_package_test_' + uuid4().hex
        self.schema = schema
        c = self.connection
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        for table in (*package.TABLES, 'risk_knowledge_objects', 'audit_events'):
            c.execute(sql.SQL('CREATE TABLE {}.{} (LIKE credit_data.{} INCLUDING ALL)').format(
                sql.Identifier(schema), sql.Identifier(table), sql.Identifier(table)))
            # LIKE copies serial defaults; immediately replace them so this test
            # never advances an operational table's sequence.
            key = 'policy_id' if table == 'policy_documents' else 'position' if table == 'risk_knowledge_objects' else 'id'
            if table == 'inventory_policies':
                continue
            seq = table + '_test_sequence'
            c.execute(sql.SQL('CREATE SEQUENCE {}.{} OWNED BY {}.{}.{}').format(
                sql.Identifier(schema), sql.Identifier(seq), sql.Identifier(schema), sql.Identifier(table), sql.Identifier(key)))
            c.execute(sql.SQL('ALTER TABLE {}.{} ALTER COLUMN {} SET DEFAULT nextval({})').format(
                sql.Identifier(schema), sql.Identifier(table), sql.Identifier(key), sql.Literal(schema + '.' + seq)))
        c.execute(sql.SQL('SET LOCAL search_path TO {}, credit_data, public').format(sql.Identifier(schema)))

    @contextmanager
    def factory(self):
        yield self.connection

    def test_fresh_import_roundtrip_idempotence_and_conflict_protection(self):
        c = self.connection
        dry = package.import_package(connection_factory=self.factory, dry_run=True)
        self.assertEqual(dry['status'], 'validated; no changes')
        self.assertEqual(c.execute('SELECT count(*) AS n FROM policy_documents').fetchone()['n'], 0)
        result = package.import_package(connection_factory=self.factory)
        self.assertEqual(result['status'], 'imported')
        self.assertEqual(result['policies'], 35)
        self.assertEqual(c.execute('SELECT count(*) AS n FROM policy_documents').fetchone()['n'], 35)
        from app.risk_knowledge.repositories import PostgreSQLRepository
        from app.risk_knowledge.semantic_pipeline import current_records
        imported = current_records(PostgreSQLRepository(self.factory, None))
        original = package.read_package()['payload']['records']
        self.assertEqual(imported, original)  # Includes evidence, scopes and all review histories.
        self.assertEqual(package.summary({'records': imported}), package.summary({'records': original}))
        self.assertTrue(all(Path(row['local_pdf_path']).is_file() for row in c.execute('SELECT local_pdf_path FROM policy_documents').fetchall()))
        self.assertTrue(all(Path(row['source_path']).is_file() for row in c.execute('SELECT source_path FROM inventory_documents').fetchall()))
        # Explicit seed IDs must not collide with later generated IDs.
        for table in ('policy_documents', 'policy_versions', 'inventory_documents', 'policy_clauses'):
            key = 'policy_id' if table == 'policy_documents' else 'id'
            maximum = c.execute(sql.SQL('SELECT max({}) AS n FROM {}').format(sql.Identifier(key), sql.Identifier(table))).fetchone()['n']
            next_id = c.execute('SELECT nextval(pg_get_serial_sequence(%s,%s)) AS n', (table, key)).fetchone()['n']
            self.assertGreater(next_id, maximum)
        again = package.import_package(connection_factory=self.factory)
        self.assertEqual(again['status'], 'already imported')
        self.assertEqual(c.execute('SELECT count(*) AS n FROM audit_events').fetchone()['n'], 1)
        with tempfile.TemporaryDirectory() as directory:
            # This test already holds a rollback-only transaction containing the
            # scratch schema. Its snapshot cannot change isolation mid-transaction.
            class Snapshot:
                def execute(self, query, *args):
                    if isinstance(query, str) and query.startswith('SET TRANSACTION'):
                        return None
                    return c.execute(query, *args)
            @contextmanager
            def snapshot():
                yield Snapshot()
            package.export_package(directory, snapshot)
            roundtrip = package.read_package(directory)['payload']
            self.assertEqual(roundtrip['records'], original)
            with self.assertRaisesRegex(ValueError, 'different knowledge package'):
                package.import_package(directory, self.factory)
            # Exercise the real polling/export path against actual SQL records.
            from app.services.policy_knowledge_auto_export import KnowledgeAutoExporter
            from psycopg.types.json import Jsonb
            worker = KnowledgeAutoExporter(directory, connection_factory=snapshot)
            self.assertFalse(worker.tick())
            changed = deepcopy(original[0])
            changed['rules'][0]['status'] = 'REJECTED'
            from app.risk_knowledge.semantic_pipeline import seal
            seal(changed)
            c.execute("UPDATE risk_knowledge_objects SET payload=%s WHERE kind='metadata' AND owner_id='' AND id=%s", (Jsonb(changed), changed['id']))
            self.assertTrue(worker.tick())
            refreshed = package.read_package(directory)['payload']['records']
            self.assertEqual(next(r for r in refreshed if r['id'] == changed['id']), changed)
            self.assertFalse(worker.tick())

    def test_partial_failure_rolls_back_all_imported_rows(self):
        c = self.connection
        class FailingConnection:
            def execute(self, query, *args):
                statement = query if isinstance(query, str) else query.as_string(c)
                if statement.startswith('INSERT INTO "policy_clauses"'):
                    raise ValueError('Injected write failure')
                return c.execute(query, *args)
        @contextmanager
        def failing_factory():
            with c.transaction():
                yield FailingConnection()
        with self.assertRaisesRegex(ValueError, 'Injected write failure'):
            package.import_package(connection_factory=failing_factory)
        for table in package.TABLES:
            self.assertEqual(c.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(sql.Identifier(table))).fetchone()['n'], 0)

    def test_nonempty_catalog_is_not_overwritten(self):
        # Inventory-only state is also protected, before any package row is written.
        self.connection.execute("INSERT INTO inventory_policies(id,code,name) VALUES (999999,'existing','Existing')")
        with self.assertRaisesRegex(ValueError, 'populated'):
            package.import_package(connection_factory=self.factory)
        self.assertEqual(self.connection.execute('SELECT count(*) AS n FROM policy_documents').fetchone()['n'], 0)
