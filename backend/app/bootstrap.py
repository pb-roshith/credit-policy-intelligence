"""Idempotent PostgreSQL bootstrap for a new application installation."""

from datetime import datetime, timezone

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from .config import (
    ADMIN_USER_ID, DATABASE_CONNECT_TIMEOUT_SECONDS, DATABASE_STATEMENT_TIMEOUT_MS,
    DATABASE_URL,
)


def _connection_options() -> dict:
    return {
        "connect_timeout": DATABASE_CONNECT_TIMEOUT_SECONDS,
        "options": f"-c statement_timeout={DATABASE_STATEMENT_TIMEOUT_MS} "
                   f"-c idle_in_transaction_session_timeout={DATABASE_STATEMENT_TIMEOUT_MS}",
    }


ACCOUNT_TABLES = (
    "borrower",
    "credit_requests",
    "borrower_exposure_history",
    "approval_authority_rules",
    "credit_request_policy_evaluations",
    "credit_request_compliance",
    "ai_compliance_reviews",
    "credit_request_exceptions",
    "dashboard_insights",
    "decision_scenarios",
    "ai_observability_spans",
)


def ensure_database_exists() -> None:
    """Create the database in DATABASE_URL when the configured role permits it."""
    target_database = conninfo_to_dict(DATABASE_URL).get("dbname")
    if not target_database:
        raise RuntimeError("DATABASE_URL must include a database name")

    try:
        connection = psycopg.connect(DATABASE_URL, **_connection_options())
    except psycopg.errors.InvalidCatalogName:
        connection = None
    if connection is not None:
        connection.close()
        return

    maintenance_url = make_conninfo(DATABASE_URL, dbname="postgres")
    try:
        with psycopg.connect(maintenance_url, autocommit=True, **_connection_options()) as maintenance:
            if maintenance.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (target_database,)
            ).fetchone():
                return
            try:
                maintenance.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_database))
                )
            except psycopg.errors.DuplicateDatabase:
                pass
    except psycopg.errors.InsufficientPrivilege as error:
        raise RuntimeError(
            f"Database {target_database!r} does not exist and the PostgreSQL role "
            "in DATABASE_URL does not have CREATEDB permission"
        ) from error


def _create_public_tables(connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS public.users (
            user_id VARCHAR(64) PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role VARCHAR(32) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked BOOLEAN NOT NULL DEFAULT FALSE,
            questions TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            approved_at TIMESTAMPTZ
        )
    """)
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_user_id_lower_idx "
        "ON public.users (LOWER(user_id))"
    )
    connection.execute("""
        CREATE TABLE IF NOT EXISTS public.password_policy (
            id SMALLINT PRIMARY KEY CHECK (id = 1),
            minimum_length INTEGER NOT NULL,
            maximum_length INTEGER NOT NULL,
            minimum_uppercase INTEGER NOT NULL,
            minimum_lowercase INTEGER NOT NULL,
            minimum_digits INTEGER NOT NULL DEFAULT 1,
            minimum_special INTEGER NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            updated_by VARCHAR(64) NOT NULL
        )
    """)
    connection.execute(
        "ALTER TABLE public.password_policy ADD COLUMN IF NOT EXISTS "
        "minimum_digits INTEGER NOT NULL DEFAULT 1"
    )
    connection.execute("""
        INSERT INTO public.password_policy (
            id, minimum_length, maximum_length, minimum_uppercase,
            minimum_lowercase, minimum_digits, minimum_special, updated_at, updated_by
        ) VALUES (1, 12, 128, 1, 1, 1, 1, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (datetime.now(timezone.utc), ADMIN_USER_ID))
    connection.execute("""
        CREATE TABLE IF NOT EXISTS public.administrative_logs (
            id BIGSERIAL PRIMARY KEY,
            actor VARCHAR(64) NOT NULL,
            action VARCHAR(80) NOT NULL,
            target VARCHAR(128),
            source_ip VARCHAR(45),
            event_type VARCHAR(16) NOT NULL DEFAULT 'event',
            outcome VARCHAR(16) NOT NULL DEFAULT 'success',
            severity VARCHAR(16) NOT NULL DEFAULT 'info',
            error_code VARCHAR(80),
            details TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute(
        "ALTER TABLE public.administrative_logs ADD COLUMN IF NOT EXISTS source_ip VARCHAR(45)"
    )
    for definition in (
        "event_type VARCHAR(16) NOT NULL DEFAULT 'event'",
        "outcome VARCHAR(16) NOT NULL DEFAULT 'success'",
        "severity VARCHAR(16) NOT NULL DEFAULT 'info'",
        "error_code VARCHAR(80)",
    ):
        connection.execute(
            "ALTER TABLE public.administrative_logs ADD COLUMN IF NOT EXISTS " + definition
        )
    connection.execute("""
        CREATE TABLE IF NOT EXISTS public.user_logs (
            event_id BIGSERIAL PRIMARY KEY,
            source_ip VARCHAR(45),
            action_owner_id VARCHAR(64) NOT NULL,
            action VARCHAR(80) NOT NULL,
            resource_id VARCHAR(128),
            event_type VARCHAR(16) NOT NULL DEFAULT 'event',
            outcome VARCHAR(16) NOT NULL DEFAULT 'success',
            severity VARCHAR(16) NOT NULL DEFAULT 'info',
            error_code VARCHAR(80),
            details TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for definition in (
        "event_type VARCHAR(16) NOT NULL DEFAULT 'event'",
        "outcome VARCHAR(16) NOT NULL DEFAULT 'success'",
        "severity VARCHAR(16) NOT NULL DEFAULT 'info'",
        "error_code VARCHAR(80)",
    ):
        connection.execute(
            "ALTER TABLE public.user_logs ADD COLUMN IF NOT EXISTS " + definition
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS user_logs_created_at_idx "
        "ON public.user_logs (created_at DESC, event_id DESC)"
    )
    connection.execute("""
        CREATE TABLE IF NOT EXISTS public.sessions (
            token_hash CHAR(64) PRIMARY KEY,
            csrf_token_hash CHAR(64) NOT NULL,
            user_id VARCHAR(64) NOT NULL,
            role VARCHAR(32) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMPTZ NOT NULL
        )
    """)
    connection.execute(
        "ALTER TABLE public.sessions ADD COLUMN IF NOT EXISTS csrf_token_hash CHAR(64)"
    )
    connection.execute(
        "UPDATE public.sessions SET csrf_token_hash = token_hash WHERE csrf_token_hash IS NULL"
    )
    connection.execute(
        "ALTER TABLE public.sessions ALTER COLUMN csrf_token_hash SET NOT NULL"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON public.sessions (LOWER(user_id))"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS sessions_expires_at_idx ON public.sessions (expires_at)"
    )


def _create_shared_tables(connection) -> None:
    connection.execute("CREATE SCHEMA IF NOT EXISTS credit_data")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS credit_data.policy_ai_configuration (
            id SMALLINT PRIMARY KEY CHECK (id = 1),
            mistral_library_id TEXT,
            mistral_agent_id TEXT,
            mistral_compliance_agent_id TEXT,
            mistral_portfolio_agent_id TEXT,
            mistral_dashboard_agent_id TEXT,
            mistral_simulator_agent_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for column in (
        "mistral_compliance_agent_id",
        "mistral_portfolio_agent_id",
        "mistral_dashboard_agent_id",
        "mistral_simulator_agent_id",
    ):
        connection.execute(
            sql.SQL("ALTER TABLE credit_data.policy_ai_configuration "
                    "ADD COLUMN IF NOT EXISTS {} TEXT").format(sql.Identifier(column))
        )
    connection.execute("""
        CREATE TABLE IF NOT EXISTS credit_data.policy_documents (
            policy_id BIGSERIAL PRIMARY KEY,
            policy_code VARCHAR(80) NOT NULL UNIQUE,
            title VARCHAR(200) NOT NULL,
            version VARCHAR(24) NOT NULL,
            policy_category VARCHAR(100) NOT NULL,
            parent_policy VARCHAR(100) NOT NULL,
            clause_number VARCHAR(16) NOT NULL,
            display_order SMALLINT NOT NULL UNIQUE,
            document_format VARCHAR(16) NOT NULL DEFAULT 'PDF',
            source_type VARCHAR(16) NOT NULL DEFAULT 'manufactured',
            policy_type VARCHAR(40),
            library_policy_id VARCHAR(16),
            effective_date DATE NOT NULL,
            status VARCHAR(24) NOT NULL,
            summary TEXT NOT NULL,
            page_count INTEGER NOT NULL CHECK (page_count > 0),
            file_name VARCHAR(255) NOT NULL UNIQUE,
            local_pdf_path TEXT NOT NULL,
            mistral_document_id TEXT NOT NULL UNIQUE,
            mistral_library_id TEXT NOT NULL,
            mistral_agent_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for definition in (
        "policy_category VARCHAR(100)", "parent_policy VARCHAR(100)",
        "clause_number VARCHAR(16)", "display_order SMALLINT",
        "document_format VARCHAR(16) NOT NULL DEFAULT 'PDF'",
        "source_type VARCHAR(16) NOT NULL DEFAULT 'manufactured'",
        "policy_type VARCHAR(40)", "library_policy_id VARCHAR(16)",
    ):
        connection.execute(
            sql.SQL("ALTER TABLE credit_data.policy_documents ADD COLUMN IF NOT EXISTS ")
            + sql.SQL(definition)
        )
    connection.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS policy_documents_library_id_unique
        ON credit_data.policy_documents (library_policy_id)
        WHERE library_policy_id IS NOT NULL
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS credit_data.policy_generation_jobs (
            job_id VARCHAR(32) PRIMARY KEY,
            status VARCHAR(16) NOT NULL CHECK (status IN ('queued','running','completed','failed')),
            total_documents SMALLINT NOT NULL DEFAULT 35,
            completed_documents SMALLINT NOT NULL DEFAULT 0,
            current_policy VARCHAR(200),
            message TEXT NOT NULL,
            error TEXT,
            initiated_by VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
    """)
    connection.execute(
        "ALTER TABLE credit_data.policy_generation_jobs "
        "ALTER COLUMN total_documents SET DEFAULT 35"
    )
    connection.execute("""
        CREATE TABLE IF NOT EXISTS credit_data.policy_controls (
            control_id VARCHAR(40) PRIMARY KEY,
            policy_id BIGINT NOT NULL REFERENCES credit_data.policy_documents(policy_id) ON DELETE CASCADE,
            policy_code VARCHAR(80) NOT NULL,
            policy_name VARCHAR(200) NOT NULL,
            control_sequence SMALLINT NOT NULL CHECK (control_sequence BETWEEN 1 AND 5),
            control_name VARCHAR(240) NOT NULL,
            control_owner VARCHAR(100) NOT NULL,
            clause_number VARCHAR(16) NOT NULL,
            control_type VARCHAR(24) NOT NULL,
            automation VARCHAR(24) NOT NULL,
            frequency VARCHAR(40) NOT NULL,
            effectiveness SMALLINT NOT NULL CHECK (effectiveness BETWEEN 0 AND 100),
            status VARCHAR(32) NOT NULL CHECK (status IN ('Effective','Needs Improvement','Ineffective')),
            last_tested DATE NOT NULL,
            failures_90d SMALLINT NOT NULL CHECK (failures_90d >= 0),
            control_description TEXT NOT NULL,
            assessment TEXT NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (policy_id, control_sequence)
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS policy_controls_policy_idx
        ON credit_data.policy_controls (policy_id, control_sequence)
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS credit_data.policy_relationships (
            relationship_id BIGSERIAL PRIMARY KEY,
            policy_id BIGINT NOT NULL REFERENCES credit_data.policy_documents(policy_id) ON DELETE CASCADE,
            related_policy_id BIGINT NOT NULL REFERENCES credit_data.policy_documents(policy_id) ON DELETE CASCADE,
            relationship_type VARCHAR(40) NOT NULL,
            relationship_strength SMALLINT NOT NULL CHECK (relationship_strength BETWEEN 1 AND 100),
            rationale TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (policy_id < related_policy_id),
            UNIQUE (policy_id, related_policy_id)
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS policy_relationships_related_idx
        ON credit_data.policy_relationships (related_policy_id, policy_id)
    """)
    connection.execute("""
        UPDATE credit_data.policy_generation_jobs
        SET status='failed', message='Generation interrupted by a backend restart',
            error='Restart the generation job to continue with missing policies.',
            finished_at=CURRENT_TIMESTAMP
        WHERE status IN ('queued', 'running')
    """)


def _create_account_tables(connection) -> None:
    connection.execute('CREATE SCHEMA IF NOT EXISTS "user"')
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".borrower (
            borrower_id BIGSERIAL,
            user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            borrower_name VARCHAR(160) NOT NULL CHECK (LENGTH(BTRIM(borrower_name)) >= 2),
            PRIMARY KEY (user_id, borrower_id)
        )
    """)
    connection.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS borrower_name_unique
        ON "user".borrower (user_id, LOWER(BTRIM(borrower_name)))
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".credit_requests (
            credit_request_number VARCHAR(24) NOT NULL,
            user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            borrower_id BIGINT NOT NULL,
            borrower_name VARCHAR(160) NOT NULL,
            industry VARCHAR(80) NOT NULL,
            geography VARCHAR(80) NOT NULL DEFAULT 'Unknown',
            exposure BIGINT NOT NULL CHECK (exposure >= 0),
            facility VARCHAR(80) NOT NULL,
            rating VARCHAR(12) NOT NULL,
            requested_amount BIGINT NOT NULL CHECK (requested_amount > 0),
            status VARCHAR(32) NOT NULL,
            compliance_score SMALLINT NOT NULL CHECK (compliance_score BETWEEN 0 AND 100),
            collateral_coverage NUMERIC(7,2) NOT NULL DEFAULT 0,
            recommended_pricing_bps INTEGER NOT NULL DEFAULT 325,
            recommended_tenor_years SMALLINT NOT NULL DEFAULT 7,
            PRIMARY KEY (user_id, credit_request_number),
            FOREIGN KEY (user_id, borrower_id) REFERENCES "user".borrower(user_id, borrower_id)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".borrower_exposure_history (
            exposure_record_id BIGSERIAL,
            user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            borrower_id BIGINT NOT NULL,
            facility_reference VARCHAR(40) NOT NULL,
            facility_type VARCHAR(80) NOT NULL,
            reporting_month DATE NOT NULL,
            original_exposure BIGINT NOT NULL CHECK (original_exposure > 0),
            scheduled_payment BIGINT NOT NULL CHECK (scheduled_payment >= 0),
            actual_payment BIGINT NOT NULL CHECK (actual_payment >= 0),
            outstanding_exposure BIGINT NOT NULL CHECK (outstanding_exposure >= 0),
            days_past_due SMALLINT NOT NULL DEFAULT 0 CHECK (days_past_due >= 0),
            payment_status VARCHAR(24) NOT NULL CHECK (payment_status IN ('Current','Delayed','Defaulted')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, exposure_record_id),
            UNIQUE (user_id, borrower_id, facility_reference, reporting_month),
            FOREIGN KEY (user_id, borrower_id) REFERENCES "user".borrower(user_id, borrower_id)
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS borrower_exposure_history_lookup_idx
        ON "user".borrower_exposure_history
        (user_id, borrower_id, facility_reference, reporting_month DESC, exposure_record_id DESC)
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".approval_authority_rules (
            user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            rule_order SMALLINT NOT NULL,
            maximum_post_approval_exposure BIGINT,
            authority_name VARCHAR(80) NOT NULL,
            authority_rank SMALLINT NOT NULL,
            PRIMARY KEY (user_id, rule_order),
            UNIQUE (user_id, authority_rank)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".credit_request_policy_evaluations (
            evaluation_id BIGSERIAL,
            user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            credit_request_number VARCHAR(24) NOT NULL,
            clause_code VARCHAR(40) NOT NULL,
            clause_name VARCHAR(160) NOT NULL,
            result VARCHAR(12) NOT NULL CHECK (result IN ('PASS','WARNING','FAIL')),
            PRIMARY KEY (user_id, evaluation_id),
            FOREIGN KEY (user_id, credit_request_number)
                REFERENCES "user".credit_requests(user_id, credit_request_number) ON DELETE CASCADE
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".credit_request_compliance (
            user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            credit_request_number VARCHAR(24) NOT NULL,
            geography_risk VARCHAR(12) NOT NULL CHECK (geography_risk IN ('Low','Medium','High')),
            concentration_limit_utilization NUMERIC(7,2) NOT NULL CHECK (concentration_limit_utilization >= 0),
            adjusted_collateral BIGINT NOT NULL CHECK (adjusted_collateral >= 0),
            post_approval_exposure BIGINT NOT NULL CHECK (post_approval_exposure > 0),
            approval_authority VARCHAR(80) NOT NULL,
            required_approval_authority VARCHAR(80) NOT NULL,
            total_required_documents INTEGER NOT NULL CHECK (total_required_documents > 0),
            uploaded_required_documents INTEGER NOT NULL CHECK (uploaded_required_documents >= 0),
            overall_score NUMERIC(5,2) NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
            compliance_status VARCHAR(40) NOT NULL,
            category_scores JSONB NOT NULL,
            findings JSONB NOT NULL,
            breached_rules JSONB NOT NULL,
            recommendations JSONB NOT NULL,
            evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, credit_request_number),
            FOREIGN KEY (user_id, credit_request_number)
                REFERENCES "user".credit_requests(user_id, credit_request_number) ON DELETE CASCADE
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".ai_compliance_reviews (
            review_id BIGSERIAL,
            user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            credit_request_number VARCHAR(24) NOT NULL,
            agent_id TEXT NOT NULL,
            review JSONB NOT NULL,
            created_by VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, review_id),
            FOREIGN KEY (user_id, credit_request_number)
                REFERENCES "user".credit_requests(user_id, credit_request_number) ON DELETE CASCADE
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS ai_compliance_reviews_request_created_idx
        ON "user".ai_compliance_reviews
        (user_id, credit_request_number, created_at DESC, review_id DESC)
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".credit_request_exceptions (
            exception_id VARCHAR(24) NOT NULL,
            user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            credit_request_number VARCHAR(24) NOT NULL,
            exception_type VARCHAR(80) NOT NULL,
            clause_code VARCHAR(40) NOT NULL,
            severity VARCHAR(16) NOT NULL,
            exposure BIGINT NOT NULL,
            owner VARCHAR(120) NOT NULL,
            due_date DATE NOT NULL,
            status VARCHAR(32) NOT NULL,
            description TEXT NOT NULL,
            rationale JSONB NOT NULL,
            workflow JSONB NOT NULL,
            history JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, exception_id),
            FOREIGN KEY (user_id, credit_request_number)
                REFERENCES "user".credit_requests(user_id, credit_request_number) ON DELETE CASCADE
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS credit_request_exceptions_request_idx
        ON "user".credit_request_exceptions (user_id, credit_request_number, created_at DESC)
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".dashboard_insights (
            user_id VARCHAR(64) PRIMARY KEY DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            insights JSONB NOT NULL CHECK (jsonb_typeof(insights)='array' AND jsonb_array_length(insights) BETWEEN 5 AND 7),
            agent_id TEXT NOT NULL,
            source_generated_at TIMESTAMPTZ NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".decision_scenarios (
            scenario_id BIGSERIAL,
            user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            scenario_name VARCHAR(120) NOT NULL CHECK (LENGTH(BTRIM(scenario_name)) > 0),
            inputs JSONB NOT NULL CHECK (jsonb_typeof(inputs)='object'),
            results JSONB NOT NULL CHECK (jsonb_typeof(results)='object'),
            recommendations JSONB NOT NULL CHECK (jsonb_typeof(recommendations)='array' AND jsonb_array_length(recommendations) BETWEEN 3 AND 5),
            agent_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, scenario_id)
        )
    """)
    connection.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS decision_scenarios_name_unique
        ON "user".decision_scenarios (user_id, LOWER(BTRIM(scenario_name)))
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS "user".ai_observability_spans (
            span_id VARCHAR(16) NOT NULL,
            trace_id VARCHAR(32) NOT NULL,
            user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id', true), ''),
            feature VARCHAR(80) NOT NULL,
            operation VARCHAR(120) NOT NULL,
            model VARCHAR(120),
            target VARCHAR(160),
            status VARCHAR(16) NOT NULL CHECK (status IN ('success','failed')),
            latency_ms NUMERIC(14,3) NOT NULL CHECK (latency_ms >= 0),
            input_tokens BIGINT,
            output_tokens BIGINT,
            total_tokens BIGINT,
            error_type VARCHAR(160),
            error_message TEXT,
            started_at TIMESTAMPTZ NOT NULL,
            ended_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (user_id, span_id)
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS ai_observability_spans_started_idx
        ON "user".ai_observability_spans (user_id, started_at DESC)
    """)
    for audit_column in (
        "input_payload TEXT",
        "output_payload TEXT",
        "retrieved_sources JSONB NOT NULL DEFAULT '[]'::jsonb",
        "flow_steps JSONB NOT NULL DEFAULT '[]'::jsonb",
    ):
        connection.execute(
            f'ALTER TABLE "user".ai_observability_spans ADD COLUMN IF NOT EXISTS {audit_column}'
        )


def _configure_account_security(connection) -> None:
    connection.execute("""
        DO $$ BEGIN
            CREATE ROLE credit_user_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    role = connection.execute(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='credit_user_runtime'"
    ).fetchone()
    if role["rolsuper"] or role["rolbypassrls"]:
        raise RuntimeError("credit_user_runtime must not bypass row-level security")
    current_role = connection.execute(
        "SELECT current_user AS role_name"
    ).fetchone()["role_name"]
    connection.execute(
        sql.SQL("GRANT credit_user_runtime TO {}").format(sql.Identifier(current_role))
    )
    connection.execute('GRANT USAGE ON SCHEMA "user" TO credit_user_runtime')
    for table in ACCOUNT_TABLES:
        identifier = sql.Identifier("user", table)
        connection.execute(sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(identifier))
        connection.execute(sql.SQL("ALTER TABLE {} FORCE ROW LEVEL SECURITY").format(identifier))
        connection.execute(sql.SQL("DROP POLICY IF EXISTS account_isolation ON {}").format(identifier))
        connection.execute(sql.SQL("""
            CREATE POLICY account_isolation ON {}
            USING (user_id = NULLIF(current_setting('app.user_id', true), ''))
            WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), ''))
        """).format(identifier))
        connection.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON {} TO credit_user_runtime")
            .format(identifier)
        )
    connection.execute(
        'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "user" TO credit_user_runtime'
    )
    connection.execute("""
        CREATE OR REPLACE VIEW "user".latest_borrower_exposure
        WITH (security_invoker=true) AS
        SELECT DISTINCT ON (user_id, borrower_id, facility_reference)
            user_id, borrower_id, facility_reference, outstanding_exposure
        FROM "user".borrower_exposure_history
        ORDER BY user_id, borrower_id, facility_reference,
                 reporting_month DESC, exposure_record_id DESC
    """)
    connection.execute(
        'GRANT SELECT ON "user".latest_borrower_exposure TO credit_user_runtime'
    )


def initialize_database() -> None:
    """Create every database object required by the backend if it is absent."""
    ensure_database_exists()
    try:
        with psycopg.connect(
            DATABASE_URL, row_factory=dict_row, **_connection_options()
        ) as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('credit_policy_bootstrap'))")
            _create_public_tables(connection)
            _create_shared_tables(connection)
            _create_account_tables(connection)
            _configure_account_security(connection)
    except psycopg.errors.InsufficientPrivilege as error:
        raise RuntimeError(
            "The PostgreSQL role in DATABASE_URL needs permission to create schemas, "
            "tables, and the credit_user_runtime role during first startup"
        ) from error
