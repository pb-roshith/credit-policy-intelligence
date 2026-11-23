"""Company/document-only package tests with rollback-only PostgreSQL imports."""
from contextlib import contextmanager, closing
from copy import deepcopy
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from psycopg import sql
from app.services.dossier_data import package


class DossierPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.envelope = package.read_package()

    def test_company_list_and_originals_exclude_all_workflow_content(self):
        payload = self.envelope['payload']
        self.assertEqual(package.counts(payload)['companies'],8)
        self.assertEqual(package.counts(payload)['company_documents'],102)
        self.assertEqual(set(payload),{'format','exported_at','mcp','provider_documents','assets'})
        self.assertEqual(set(payload['mcp']),{'public.mcp_companies','public.mcp_documents'})
        for company in payload['mcp']['public.mcp_companies']:
            self.assertEqual(set(company),set(package.COMPANY_FIELDS))
            self.assertNotIn('context',company)
        for resource in payload['provider_documents']:
            self.assertTrue(package.asset_path(package.directory(),resource['asset']).read_bytes().startswith(b'%PDF'))

    def test_export_reads_only_mcp_and_filters_company_context(self):
        company = deepcopy(self.envelope['payload']['mcp']['public.mcp_companies'][0])
        company['context'] = {'narrative':'must not be packaged','financials':{'amount':100}}
        connection=MagicMock()
        connection.execute.side_effect=[MagicMock(),MagicMock(fetchall=lambda:[company]),MagicMock(fetchall=lambda:[])]
        @contextmanager
        def factory():
            yield connection
        with tempfile.TemporaryDirectory() as folder:
            result=package.export_package(folder,mcp_factory=factory)
            value=package.read_package(folder)['payload']
            self.assertEqual(result['companies'],1)
            self.assertNotIn('context',value['mcp']['public.mcp_companies'][0])
            self.assertNotIn('must not be packaged',package.encode(value))

    def test_manifest_tampering_is_rejected(self):
        value=deepcopy(self.envelope)
        value['payload']['mcp']['public.mcp_companies'][0]['name']='Changed'
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/package.MANIFEST).write_text(package.encode(value),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'package checksum'):
                package.read_package(folder)

    def test_document_bytes_are_required(self):
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(FileNotFoundError):
            package.validate_payload(self.envelope['payload'],folder)

    def test_narratives_or_extra_financial_columns_are_rejected(self):
        for mutate in (
            lambda p:p.update(narratives=['unwanted']),
            lambda p:p['mcp']['public.mcp_companies'][0].update(context={'financials':'unwanted'}),
            lambda p:p['mcp'].update({'public.deals':[]}),
        ):
            value=deepcopy(self.envelope['payload']);mutate(value)
            with self.assertRaises(ValueError):
                package.validate_payload(value,package.directory())

    def test_path_traversal_is_rejected(self):
        for name in ('../outside','files/../../outside','files/..\\outside','C:/outside'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                package.asset_path(package.directory(),name)

    def test_document_company_links_are_validated(self):
        value=deepcopy(self.envelope['payload'])
        value['mcp']['public.mcp_documents'][0]['company_id']=-1
        with self.assertRaisesRegex(ValueError,'missing company'):
            package.validate_payload(value,package.directory())

    def test_gemini_restores_only_original_documents_and_is_idempotent(self):
        payload=self.envelope['payload']
        with tempfile.TemporaryDirectory() as folder:
            store=Path(folder)/'gemini.sqlite3'
            package.restore_gemini(payload,package.directory(),store)
            package.restore_gemini(payload,package.directory(),store)
            with closing(sqlite3.connect(store)) as c,c:
                self.assertEqual(c.execute("SELECT count(*) FROM resources WHERE kind='document'").fetchone()[0],102)
                self.assertEqual(c.execute("SELECT count(*) FROM resources WHERE kind NOT IN ('document','library')").fetchone()[0],0)
                first=payload['provider_documents'][0]
                content=c.execute('SELECT content FROM resources WHERE id=?',(first['document_id'],)).fetchone()[0]
                self.assertEqual(content,package.asset_path(package.directory(),first['asset']).read_bytes())
                c.execute('UPDATE resources SET content=? WHERE id=?',(b'conflicting bytes',first['document_id']))
            with self.assertRaisesRegex(ValueError,'conflicts'):
                package.restore_gemini(payload,package.directory(),store)

    def test_existing_catalog_skips_startup_import(self):
        db=MagicMock()
        db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'exists':1}
        with patch.object(package,'import_mcp') as load:
            package.autoload_mcp(db)
            load.assert_not_called()


class Scratch:
    """Redirect every production schema reference to transaction-local clones."""
    def __init__(self, connection, names):
        self.connection, self.names = connection, names

    def execute(self, query, parameters=None):
        statement = query if isinstance(query,str) else query.as_string(self.connection)
        if statement.startswith('SET TRANSACTION'):
            return None  # Test already owns a rollback-only scratch transaction.
        for original, scratch in self.names.items():
            statement = statement.replace(f'"{original}".', f'"{scratch}".').replace(original+'.',scratch+'.')
        if parameters:
            parameters = list(parameters)
            for i,value in enumerate(parameters):
                if isinstance(value,str):
                    if value in self.names:
                        parameters[i] = self.names[value]
                    else:
                        for original,scratch in self.names.items():
                            if value.startswith(original+'.'):
                                parameters[i] = scratch + value[len(original):]
        return self.connection.execute(statement, parameters)


@unittest.skipUnless(os.getenv('RUN_DOSSIER_PACKAGE_DB_TESTS') == '1', 'Enable rollback-only Dossier package database tests')
class DossierPackageDatabaseTests(unittest.TestCase):
    def make_scratch(self, factory, tables):
        manager = factory()
        c = manager.__enter__()
        # Rollback before exiting either context; no application rows are changed.
        self.addCleanup(manager.__exit__, None, None, None)
        self.addCleanup(c.rollback)
        names = {name: 'dossier_test_' + name + '_' + uuid4().hex for name in ('public','audit','credit_dossier')}
        for schema in names.values():
            c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        for table in tables:
            schema, name = table.split('.')
            c.execute(sql.SQL('CREATE TABLE {}.{} (LIKE {} INCLUDING ALL)').format(sql.Identifier(names[schema]),sql.Identifier(name),package.identifier(table)))
            serial = c.execute("SELECT pg_get_serial_sequence(%s,'id') AS seq",(table,)).fetchone()['seq']
            if serial:
                seq = name + '_test_seq'
                c.execute(sql.SQL('CREATE SEQUENCE {}.{} OWNED BY {}.{}.id').format(sql.Identifier(names[schema]),sql.Identifier(seq),sql.Identifier(names[schema]),sql.Identifier(name)))
                c.execute(sql.SQL('ALTER TABLE {}.{} ALTER COLUMN id SET DEFAULT nextval({})').format(sql.Identifier(names[schema]),sql.Identifier(name),sql.Literal(names[schema]+'.'+seq)))
        c.execute(sql.SQL('SET LOCAL search_path TO {},{},{}').format(*(sql.Identifier(names[s]) for s in ('public','audit','credit_dossier'))))
        wrapped = Scratch(c, names)
        # Add the actual foreign keys to the cloned tables too.
        for table in tables:
            constraints = c.execute("SELECT conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE conrelid=%s::regclass AND contype='f'",(table,)).fetchall()
            for constraint in constraints:
                wrapped.execute(sql.SQL('ALTER TABLE {} ADD CONSTRAINT {} ').format(package.identifier(table),sql.Identifier(constraint['conname'])).as_string(c)+constraint['definition'])
        @contextmanager
        def scratch_factory():
            yield wrapped
        return c, wrapped, scratch_factory

    def test_import_restores_only_companies_and_documents(self):
        with package.mcp_connection() as source:
            finance=['credit_dossier.'+r['table_name'] for r in source.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='credit_dossier' AND table_type='BASE TABLE'").fetchall()]
        c,db,factory=self.make_scratch(package.mcp_connection,(*package.TABLES,*finance))
        dry=package.import_mcp(factory=factory,dry_run=True,ai_provider='mistral')
        self.assertIn('validated',dry['status'])
        result=package.import_mcp(factory=factory,ai_provider='mistral')
        self.assertEqual(result['companies'],8)
        rows=db.execute('SELECT local_path FROM mcp_documents').fetchall()
        self.assertEqual(len(rows),102)
        self.assertTrue(all(Path(r['local_path']).is_file() for r in rows))
        self.assertTrue(all(r['context']=={} for r in db.execute('SELECT context FROM mcp_companies').fetchall()))
        for name in finance:
            self.assertEqual(db.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(package.identifier(name))).fetchone()['n'],0)
        source=package.read_package()['payload']
        self.assertGreater(db.execute("SELECT nextval(pg_get_serial_sequence('public.mcp_documents','id')) AS n").fetchone()['n'],max(r['id'] for r in source['mcp']['public.mcp_documents']))
        self.assertEqual(package.import_mcp(factory=factory,ai_provider='mistral')['status'],'already imported')

    def test_import_failure_rolls_back_all_company_rows(self):
        c,db,factory=self.make_scratch(package.mcp_connection,package.TABLES)
        insert=package._insert
        def fail(connection,name,row):
            if name=='public.mcp_documents':
                raise ValueError('Injected write failure')
            return insert(connection,name,row)
        with self.assertRaisesRegex(ValueError,'Injected write failure'),c.transaction():
            with patch.object(package,'_insert',side_effect=fail):
                package.import_mcp(factory=factory,ai_provider='mistral')
        self.assertEqual(db.execute('SELECT count(*) AS n FROM mcp_companies').fetchone()['n'],0)

    def test_nonempty_catalog_is_preserved(self):
        c,db,factory=self.make_scratch(package.mcp_connection,package.TABLES)
        company=deepcopy(package.read_package()['payload']['mcp']['public.mcp_companies'][0])
        package._insert(db,'public.mcp_companies',company)
        with self.assertRaisesRegex(ValueError,'empty MCP'):
            package.import_mcp(factory=factory,ai_provider='mistral')
        self.assertEqual(db.execute('SELECT count(*) AS n FROM mcp_companies').fetchone()['n'],1)
        self.assertEqual(db.execute('SELECT count(*) AS n FROM mcp_documents').fetchone()['n'],0)
