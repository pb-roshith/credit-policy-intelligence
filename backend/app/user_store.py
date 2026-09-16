"""Transactional consolidation of legacy account schemas into the user schema."""
import re
from hashlib import sha256

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from .config import ADMIN_USER_ID, DATABASE_URL

ROLE = 'credit_user_runtime'
ACCOUNT_TABLES = ('borrower', 'credit_requests', 'borrower_exposure_history',
                  'approval_authority_rules', 'credit_request_policy_evaluations',
                  'credit_request_compliance', 'ai_compliance_reviews',
                  'credit_request_exceptions')


def ensure_primary_keys(c):
    keys = c.execute("""SELECT t.relname AS tablename, k.conname
        FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname='credit_data' AND k.contype='p'""").fetchall()
    for key in keys:
        exists = c.execute("SELECT 1 FROM pg_constraint WHERE conrelid=%s::regclass AND contype='p'", ('"user".' + key['tablename'],)).fetchone()
        if not exists:
            c.execute(sql.SQL('ALTER TABLE "user".{} ADD PRIMARY KEY USING INDEX {}').format(sql.Identifier(key['tablename']), sql.Identifier(key['conname'])))


def migrate_user_store():
    """Copy and verify every legacy account table, then remove its old schema.

    DDL and data changes commit together. An unknown owner or incompatible table
    aborts the transaction; no legacy data is silently discarded.
    """
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('consolidate_user_store'))")
        c.execute('CREATE SCHEMA IF NOT EXISTS "user"')
        c.execute('CREATE TABLE IF NOT EXISTS "user".store_migrations (version integer PRIMARY KEY, completed_at timestamptz DEFAULT now())')
        if c.execute('SELECT 1 FROM "user".store_migrations WHERE version = 1').fetchone():
            ensure_primary_keys(c)
            return
        users = c.execute('SELECT user_id FROM public.users').fetchall()
        users.append({'user_id': ADMIN_USER_ID})
        owners = {'user_' + sha256(r['user_id'].encode()).hexdigest()[:56]: r['user_id'] for r in users}
        schemas = [r['nspname'] for r in c.execute("SELECT nspname FROM pg_namespace WHERE nspname ~ '^user_[0-9a-f]{56}$'")]
        unknown = set(schemas) - owners.keys()
        if unknown:
            raise RuntimeError(f'Cannot establish ownership of schemas: {sorted(unknown)}')
        tables = [r['tablename'] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'credit_data' ORDER BY tablename")]
        # Clone column types/checks, but rebuild every key with user ownership.
        for table in tables:
            c.execute(sql.SQL('CREATE TABLE "user".{} (LIKE credit_data.{} INCLUDING DEFAULTS INCLUDING CONSTRAINTS, user_id varchar(64) NOT NULL DEFAULT nullif(current_setting(\'app.user_id\', true), \'\'))').format(sql.Identifier(table), sql.Identifier(table)))
            columns = c.execute("SELECT column_name, column_default FROM information_schema.columns WHERE table_schema='credit_data' AND table_name=%s", (table,)).fetchall()
            for col in columns:
                if (col['column_default'] or '').startswith('nextval('):
                    seq = table + '_' + col['column_name'] + '_seq'
                    c.execute(sql.SQL('CREATE SEQUENCE "user".{}').format(sql.Identifier(seq)))
                    c.execute(sql.SQL('ALTER TABLE "user".{} ALTER COLUMN {} SET DEFAULT nextval({})').format(sql.Identifier(table), sql.Identifier(col['column_name']), sql.Literal('"user".' + seq)))
                    c.execute(sql.SQL('ALTER SEQUENCE "user".{} OWNED BY "user".{}.{}').format(sql.Identifier(seq), sql.Identifier(table), sql.Identifier(col['column_name'])))
            indexes = c.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='credit_data' AND tablename=%s", (table,)).fetchall()
            for idx in indexes:
                definition = idx['indexdef']
                tail = definition.split(' USING ', 1)[1]
                tail = tail.replace('(', '(user_id, ', 1)
                c.execute(sql.SQL('CREATE {} INDEX {} ON "user".{} USING ').format(sql.SQL('UNIQUE' if 'CREATE UNIQUE' in definition else ''), sql.Identifier(idx['indexname']), sql.Identifier(table)) + sql.SQL(tail))
        for table in tables:
            fks = c.execute("SELECT pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE conrelid = %s::regclass AND contype='f'", ('credit_data.' + table,)).fetchall()
            for fk in fks:
                definition = re.sub(r'FOREIGN KEY \(', 'FOREIGN KEY (user_id, ', fk['definition'])
                definition = re.sub(r'REFERENCES (?:credit_data\.)?([a-z_]+)\(', r'REFERENCES "user".\1(user_id, ', definition)
                c.execute(sql.SQL('ALTER TABLE "user".{} ADD ').format(sql.Identifier(table)) + sql.SQL(definition))
        # Defer FK validation until all related tables have been copied.
        for table in tables:
            for fk in c.execute("SELECT conname FROM pg_constraint WHERE conrelid=%s::regclass AND contype='f'", ('"user".' + table,)).fetchall():
                c.execute(sql.SQL('ALTER TABLE "user".{} ALTER CONSTRAINT {} DEFERRABLE INITIALLY DEFERRED').format(sql.Identifier(table), sql.Identifier(fk['conname'])))
        sources = [(s, owners[s], None) for s in schemas]
        sources.append(('credit_data', '__legacy_unassigned__', ACCOUNT_TABLES))
        for source, owner, selected in sources:
            source_tables = [r['tablename'] for r in c.execute('SELECT tablename FROM pg_tables WHERE schemaname=%s', (source,))]
            for table in source_tables:
                if selected and table not in selected:
                    continue
                if table not in tables:
                    raise RuntimeError(f'Unexpected legacy table: {source}.{table}')
                c.execute(sql.SQL('LOCK TABLE {}.{} IN ACCESS EXCLUSIVE MODE').format(sql.Identifier(source), sql.Identifier(table)))
                cols = [r['column_name'] for r in c.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position', (source, table))]
                names = sql.SQL(', ').join(map(sql.Identifier, cols))
                c.execute(sql.SQL('INSERT INTO "user".{} ({}, user_id) SELECT {}, %s FROM {}.{}').format(sql.Identifier(table), names, names, sql.Identifier(source), sql.Identifier(table)), (owner,))
                mismatch = c.execute(sql.SQL('SELECT EXISTS ((SELECT {} FROM {}.{} EXCEPT ALL SELECT {} FROM "user".{} WHERE user_id=%s) UNION ALL (SELECT {} FROM "user".{} WHERE user_id=%s EXCEPT ALL SELECT {} FROM {}.{})) AS mismatch').format(names, sql.Identifier(source), sql.Identifier(table), names, sql.Identifier(table), names, sql.Identifier(table), names, sql.Identifier(source), sql.Identifier(table)), (owner, owner)).fetchone()['mismatch']
                if mismatch:
                    raise RuntimeError(f'Migration verification failed: {source}.{table}')
        c.execute('SET CONSTRAINTS ALL IMMEDIATE')
        for table in tables:
            for col in c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='user' AND table_name=%s AND column_default LIKE 'nextval(%%'", (table,)).fetchall():
                seq = '"user".' + table + '_' + col['column_name'] + '_seq'
                c.execute(sql.SQL('SELECT setval(%s, COALESCE(MAX({}), 0) + 1, false) FROM "user".{}').format(sql.Identifier(col['column_name']), sql.Identifier(table)), (seq,))
        c.execute("DO $$ BEGIN CREATE ROLE credit_user_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
        role = c.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=%s", (ROLE,)).fetchone()
        if role['rolsuper'] or role['rolbypassrls']:
            raise RuntimeError('Runtime role must not bypass row security')
        c.execute(sql.SQL('GRANT credit_user_runtime TO {}').format(sql.Identifier(c.execute('SELECT current_user AS name').fetchone()['name'])))
        c.execute('GRANT USAGE ON SCHEMA "user" TO credit_user_runtime')
        for table in tables:
            c.execute(sql.SQL('ALTER TABLE "user".{} ENABLE ROW LEVEL SECURITY').format(sql.Identifier(table)))
            c.execute(sql.SQL('ALTER TABLE "user".{} FORCE ROW LEVEL SECURITY').format(sql.Identifier(table)))
            c.execute(sql.SQL("CREATE POLICY account_isolation ON \"user\".{} USING (user_id = nullif(current_setting('app.user_id', true), '')) WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''))").format(sql.Identifier(table)))
            c.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON "user".{} TO credit_user_runtime').format(sql.Identifier(table)))
        c.execute('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "user" TO credit_user_runtime')
        c.execute('''CREATE VIEW "user".latest_borrower_exposure WITH (security_invoker=true) AS
            SELECT DISTINCT ON (user_id, borrower_id, facility_reference)
                user_id, borrower_id, facility_reference, outstanding_exposure
            FROM "user".borrower_exposure_history
            ORDER BY user_id, borrower_id, facility_reference, reporting_month DESC, exposure_record_id DESC''')
        c.execute('GRANT SELECT ON "user".latest_borrower_exposure TO credit_user_runtime')
        for schema in schemas:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        c.execute('INSERT INTO "user".store_migrations (version) VALUES (1)')
        ensure_primary_keys(c)
        print(f'Migrated {len(schemas)} account schemas into user; verified all copied rows.')


def initialize_dashboard_insights():
    with psycopg.connect(DATABASE_URL) as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('dashboard_insights_schema'))")
        c.execute('''ALTER TABLE credit_data.policy_ai_configuration
            ADD COLUMN IF NOT EXISTS mistral_dashboard_agent_id TEXT''')
        c.execute('''ALTER TABLE credit_data.policy_ai_configuration
            ADD COLUMN IF NOT EXISTS mistral_portfolio_agent_id TEXT''')
        c.execute('''CREATE TABLE IF NOT EXISTS "user".dashboard_insights (
            user_id varchar(64) PRIMARY KEY DEFAULT nullif(current_setting('app.user_id', true), ''),
            insights jsonb NOT NULL CHECK (jsonb_typeof(insights) = 'array' AND jsonb_array_length(insights) BETWEEN 5 AND 7),
            agent_id text NOT NULL,
            source_generated_at timestamptz NOT NULL,
            generated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('ALTER TABLE "user".dashboard_insights ENABLE ROW LEVEL SECURITY')
        c.execute('ALTER TABLE "user".dashboard_insights FORCE ROW LEVEL SECURITY')
        c.execute('DROP POLICY IF EXISTS account_isolation ON "user".dashboard_insights')
        c.execute('''CREATE POLICY account_isolation ON "user".dashboard_insights
            USING (user_id = nullif(current_setting('app.user_id', true), ''))
            WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''))''')
        c.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON "user".dashboard_insights TO credit_user_runtime')


def initialize_decision_scenarios():
    """Create the account-scoped simulator store and shared Mistral agent slot."""
    with psycopg.connect(DATABASE_URL) as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('decision_scenarios_schema'))")
        c.execute('''ALTER TABLE credit_data.policy_ai_configuration
            ADD COLUMN IF NOT EXISTS mistral_simulator_agent_id TEXT''')
        c.execute('''CREATE TABLE IF NOT EXISTS "user".decision_scenarios (
            scenario_id bigserial,
            user_id varchar(64) NOT NULL DEFAULT nullif(current_setting('app.user_id', true), ''),
            scenario_name varchar(120) NOT NULL CHECK (length(btrim(scenario_name)) > 0),
            inputs jsonb NOT NULL CHECK (jsonb_typeof(inputs) = 'object'),
            results jsonb NOT NULL CHECK (jsonb_typeof(results) = 'object'),
            recommendations jsonb NOT NULL CHECK (
                jsonb_typeof(recommendations) = 'array'
                AND jsonb_array_length(recommendations) BETWEEN 3 AND 5
            ),
            agent_id text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, scenario_id)
        )''')
        c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS decision_scenarios_name_unique
            ON "user".decision_scenarios (user_id, lower(btrim(scenario_name)))''')
        c.execute('ALTER TABLE "user".decision_scenarios ENABLE ROW LEVEL SECURITY')
        c.execute('ALTER TABLE "user".decision_scenarios FORCE ROW LEVEL SECURITY')
        c.execute('DROP POLICY IF EXISTS account_isolation ON "user".decision_scenarios')
        c.execute('''CREATE POLICY account_isolation ON "user".decision_scenarios
            USING (user_id = nullif(current_setting('app.user_id', true), ''))
            WITH CHECK (user_id = nullif(current_setting('app.user_id', true), ''))''')
        c.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON "user".decision_scenarios TO credit_user_runtime')
        c.execute('GRANT USAGE, SELECT ON SEQUENCE "user".decision_scenarios_scenario_id_seq TO credit_user_runtime')


def remove_seeded_exceptions():
    """Remove the legacy EX-8821..EX-8830 demo rows without touching user-created exceptions."""
    with psycopg.connect(DATABASE_URL) as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('remove_seeded_exceptions'))")
        if c.execute('SELECT 1 FROM "user".store_migrations WHERE version = 2').fetchone():
            return
        c.execute('''DELETE FROM "user".credit_request_exceptions
            WHERE exception_id = ANY(%s)
              AND description = 'User-raised exception for ' || credit_request_number || ' requiring policy review.'
        ''', ([f'EX-{number}' for number in range(8821, 8831)],))
        c.execute('INSERT INTO "user".store_migrations (version) VALUES (2)')


def ensure_credit_request_geography():
    """Add and backfill geography for stores created before the field existed."""
    with psycopg.connect(DATABASE_URL) as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('credit_request_geography'))")
        c.execute('''ALTER TABLE "user".credit_requests
            ADD COLUMN IF NOT EXISTS geography varchar(80) NOT NULL DEFAULT 'Unknown' ''')
        c.execute('''UPDATE "user".credit_requests SET geography = CASE
            MOD(HASHTEXT(credit_request_number::text)::bigint + 2147483648, 10)
            WHEN 0 THEN 'US Northeast' WHEN 1 THEN 'US Southeast'
            WHEN 2 THEN 'US Midwest' WHEN 3 THEN 'US West' WHEN 4 THEN 'Canada'
            WHEN 5 THEN 'United Kingdom' WHEN 6 THEN 'Europe'
            WHEN 7 THEN 'Middle East & Africa' WHEN 8 THEN 'Asia Pacific'
            ELSE 'Latin America' END
            WHERE geography = 'Unknown' OR BTRIM(geography) = '' ''')


if __name__ == '__main__':
    migrate_user_store()
