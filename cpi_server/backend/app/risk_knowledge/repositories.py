"""SQLite persistence with distinct stores and append-only reviewer audit records."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TABLES = ('documents', 'clauses', 'taxonomy_concepts', 'ontology_relationships',
          'policy_rules', 'credit_requests', 'rule_evaluation_results')


class SQLiteRepository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            for table in TABLES:
                db.execute(f'CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS metadata (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _check(self, table):
        if table not in (*TABLES, 'metadata'):
            raise ValueError('Unknown store')

    def all(self, table):
        self._check(table)
        with self.connection() as db:
            return [json.loads(r['payload']) for r in db.execute(f'SELECT payload FROM {table} ORDER BY rowid')]

    def get(self, table, identifier):
        self._check(table)
        with self.connection() as db:
            row = db.execute(f'SELECT payload FROM {table} WHERE id=?', (identifier,)).fetchone()
        return json.loads(row['payload']) if row else None

    def put(self, table, identifier, item, audit=None):
        self.put_many(table, [(identifier, item)], audit)

    def compare_and_put(self,table,identifier,item,expected_digest,audit=None):
        self._check(table)
        payload=json.dumps(item,ensure_ascii=False,allow_nan=False)
        with self.connection() as db:
            if expected_digest is None:
                result=db.execute(f'INSERT INTO {table}(id,payload) VALUES (?,?) ON CONFLICT(id) DO NOTHING',(identifier,payload))
            else:
                result=db.execute(f"UPDATE {table} SET payload=? WHERE id=? AND json_extract(payload,'$.content_digest')=?",(payload,identifier,expected_digest))
            if result.rowcount!=1:return False
            if audit:db.execute('INSERT INTO audit(occurred_at,payload) VALUES (?,?)',(datetime.now(timezone.utc).isoformat(),json.dumps(audit,ensure_ascii=False)))
        return True

    def put_new(self, table, identifier, item):
        self._check(table)
        with self.connection() as db:
            cursor=db.execute(f'INSERT INTO {table}(id,payload) VALUES (?,?) ON CONFLICT(id) DO NOTHING',
                              (identifier,json.dumps(item,ensure_ascii=False,allow_nan=False)))
            return cursor.rowcount==1

    def put_many(self, table, items, audit=None):
        self._check(table)
        with self.connection() as db:
            db.executemany(f'INSERT INTO {table} (id,payload) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                           [(key, json.dumps(value, ensure_ascii=False, allow_nan=False)) for key, value in items])
            if audit:
                db.execute('INSERT INTO audit (occurred_at,payload) VALUES (?,?)',
                           (datetime.now(timezone.utc).isoformat(), json.dumps(audit, ensure_ascii=False)))

    def audit(self):
        with self.connection() as db:
            return [dict(r) | {'payload': json.loads(r['payload'])} for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]


class PostgreSQLRepository:
    """Use CPI's shared policy connection and audit table, with private request records."""
    PRIVATE = {'credit_requests', 'rule_evaluation_results'}

    def __init__(self, connection_factory, owner_id):
        self.connection_factory = connection_factory
        self.owner_id = owner_id

    def _owner(self, table):
        if table not in (*TABLES, 'metadata'):
            raise ValueError('Unknown store')
        if table in self.PRIVATE and not self.owner_id:
            raise ValueError('An authenticated account is required')
        return self.owner_id if table in self.PRIVATE else ''

    def all(self, table):
        owner = self._owner(table)
        with self.connection_factory() as db:
            return [r['payload'] for r in db.execute('SELECT payload FROM risk_knowledge_objects WHERE kind=%s AND owner_id=%s ORDER BY position', (table, owner)).fetchall()]

    def get(self, table, identifier):
        owner = self._owner(table)
        with self.connection_factory() as db:
            row = db.execute('SELECT payload FROM risk_knowledge_objects WHERE kind=%s AND owner_id=%s AND id=%s', (table, owner, identifier)).fetchone()
        return row['payload'] if row else None

    def put(self, table, identifier, item, audit=None):
        self.put_many(table, [(identifier, item)], audit)

    def compare_and_put(self,table,identifier,item,expected_digest,audit=None):
        from psycopg.types.json import Jsonb
        owner=self._owner(table)
        with self.connection_factory() as db:
            if expected_digest is None:
                result=db.execute('INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES (%s,%s,%s,%s) ON CONFLICT(kind,owner_id,id) DO NOTHING',(table,owner,identifier,Jsonb(item)))
            else:
                result=db.execute("UPDATE risk_knowledge_objects SET payload=%s WHERE kind=%s AND owner_id=%s AND id=%s AND payload->>'content_digest'=%s",(Jsonb(item),table,owner,identifier,expected_digest))
            if result.rowcount!=1:return False
            if audit:
                db.execute('INSERT INTO audit_events(entity_type,entity_id,new_value,action,actor,reason) VALUES (%s,%s,%s,%s,%s,%s)',
                           ('RiskKnowledge:'+table,str(audit.get('entity_id',identifier)),Jsonb(audit),audit.get('action','Update'),audit.get('actor',self.owner_id),audit.get('notes','Conditional knowledge update')))
        return True

    def put_new(self, table, identifier, item):
        from psycopg.types.json import Jsonb
        owner=self._owner(table)
        with self.connection_factory() as db:
            cursor=db.execute('INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES (%s,%s,%s,%s) ON CONFLICT(kind,owner_id,id) DO NOTHING',
                              (table,owner,identifier,Jsonb(item)))
            return cursor.rowcount==1

    def put_many(self, table, items, audit=None):
        from psycopg.types.json import Jsonb
        owner = self._owner(table)
        with self.connection_factory() as db:
            with db.cursor() as cursor:
                cursor.executemany('INSERT INTO risk_knowledge_objects(kind,owner_id,id,payload) VALUES (%s,%s,%s,%s) ON CONFLICT(kind,owner_id,id) DO UPDATE SET payload=EXCLUDED.payload',
                                   [(table, owner, identifier, Jsonb(value)) for identifier, value in items])
            if audit:
                db.execute("INSERT INTO audit_events(entity_type,entity_id,new_value,action,actor,reason) VALUES (%s,%s,%s,%s,%s,%s)",
                           ('RiskKnowledge:' + table, str(audit.get('entity_id', 'collection')), Jsonb(audit),
                            audit.get('action', audit.get('after_status', 'Review')), audit.get('actor',self.owner_id),
                            audit.get('notes', 'Risk knowledge review')))

    def audit(self):
        with self.connection_factory() as db:
            rows = db.execute("SELECT id,created_at,new_value FROM audit_events WHERE entity_type LIKE 'RiskKnowledge:%%' ORDER BY id DESC LIMIT 100").fetchall()
        return [{'id': r['id'], 'occurred_at': r['created_at'].isoformat(), 'payload': r['new_value']} for r in rows]
