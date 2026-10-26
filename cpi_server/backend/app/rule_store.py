from pathlib import Path


def create_rule_tables(connection):
    # Rename the original version table while keeping its old API-facing name
    # as an updatable view. PostgreSQL preserves existing foreign keys.
    connection.execute("""DO $$ BEGIN
        IF to_regclass('credit_data.policy_rule_versions') IS NULL
           AND EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                      WHERE n.nspname='credit_data' AND c.relname='policy_rules' AND c.relkind='r') THEN
            ALTER TABLE credit_data.policy_rules RENAME TO policy_rule_versions;
        END IF;
    END $$""")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS credit_data.policy_rule_versions (
            id BIGSERIAL PRIMARY KEY, rule_key TEXT NOT NULL, version INTEGER NOT NULL,
            policy_id BIGINT NOT NULL REFERENCES credit_data.policy_documents(policy_id),
            policy_version TEXT NOT NULL, policy_fingerprint TEXT NOT NULL,
            definition JSONB NOT NULL, status TEXT NOT NULL DEFAULT 'Draft',
            active BOOLEAN NOT NULL DEFAULT false, effective_from DATE NOT NULL,
            effective_to DATE, approved_by TEXT, approval_date TIMESTAMPTZ,
            created_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(rule_key,version), CHECK(effective_to IS NULL OR effective_to>=effective_from)
        );
        ALTER TABLE credit_data.policy_rule_versions ADD COLUMN IF NOT EXISTS policy_fingerprint TEXT;
        UPDATE credit_data.policy_rule_versions SET policy_fingerprint='' WHERE policy_fingerprint IS NULL;
        ALTER TABLE credit_data.policy_rule_versions ALTER COLUMN policy_fingerprint SET NOT NULL;
        CREATE TABLE IF NOT EXISTS credit_data.policy_rule_audit (
            id BIGSERIAL PRIMARY KEY, rule_id BIGINT NOT NULL REFERENCES credit_data.policy_rule_versions(id),
            actor TEXT NOT NULL, action TEXT NOT NULL, comment TEXT NOT NULL, snapshot JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def create_inventory_tables(connection):
    for migration in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
        connection.execute(migration.read_text(encoding='utf-8-sig'))
