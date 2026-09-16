from datetime import datetime, timezone
from contextvars import ContextVar
from threading import Lock

from fastapi import HTTPException
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from .config import ADMIN_USER_ID, DATABASE_URL

data_schema = ContextVar("data_schema", default="credit_data")
account_user_id = ContextVar("account_user_id", default=None)
_initialized_schemas = set()
_initialization_lock = Lock()


def ensure_database_exists():
    """Create the database named in DATABASE_URL when it is not present yet."""
    target_database = conninfo_to_dict(DATABASE_URL).get("dbname")
    if not target_database:
        raise RuntimeError("DATABASE_URL must include a database name")

    try:
        connection = psycopg.connect(DATABASE_URL)
    except psycopg.errors.InvalidCatalogName:
        pass
    else:
        connection.close()
        return

    maintenance_url = make_conninfo(DATABASE_URL, dbname="postgres")
    try:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            database_exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (target_database,),
            ).fetchone()
            if database_exists:
                return
            try:
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_database))
                )
            except psycopg.errors.DuplicateDatabase:
                # Another backend process may have created it concurrently.
                pass
    except psycopg.errors.InsufficientPrivilege as error:
        raise RuntimeError(
            f"Database {target_database!r} does not exist and the PostgreSQL user "
            "in DATABASE_URL does not have permission to create it"
        ) from error


def db_connection():
    connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        owner = account_user_id.get()
        if owner is not None:
            if not owner or owner == '__legacy_unassigned__':
                raise HTTPException(status_code=403, detail='Account data access is unavailable')
            connection.execute(sql.SQL('SET LOCAL app.user_id TO {}').format(sql.Literal(owner)))
            connection.execute('SET LOCAL ROLE credit_user_runtime')
            connection.execute('SET LOCAL search_path TO "user"')
            return connection
        connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(
            sql.Identifier(data_schema.get())
        ))
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


def initialize_user_store():
    from .user_store import (
        ensure_credit_request_geography,
        initialize_dashboard_insights,
        initialize_decision_scenarios,
        migrate_user_store,
        remove_seeded_exceptions,
    )
    with _initialization_lock:
        if 'user' not in _initialized_schemas:
            migrate_user_store()
            ensure_credit_request_geography()
            initialize_dashboard_insights()
            initialize_decision_scenarios()
            remove_seeded_exceptions()
            _initialized_schemas.add('user')
    if account_user_id.get() is not None:
        with db_connection() as connection:
            connection.execute("""INSERT INTO approval_authority_rules
                (rule_order, maximum_post_approval_exposure, authority_name, authority_rank)
                VALUES (1,25000000,'Credit Officer',1), (2,75000000,'Senior Credit Officer',2),
                (3,150000000,'Credit Committee',3), (4,NULL,'Executive Committee',4)
                ON CONFLICT (user_id, rule_order) DO NOTHING""")


def init_auth_db():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        connection.execute("SET LOCAL search_path TO public")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
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
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_user_id_lower_idx ON users (LOWER(user_id))")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS password_policy (
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
        connection.execute("""
            ALTER TABLE password_policy
            ADD COLUMN IF NOT EXISTS minimum_digits INTEGER NOT NULL DEFAULT 1
        """)
        connection.execute("""
            INSERT INTO password_policy (
                id, minimum_length, maximum_length, minimum_uppercase,
                minimum_lowercase, minimum_digits, minimum_special, updated_at, updated_by
            ) VALUES (1, 12, 128, 1, 1, 1, 1, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (datetime.now(timezone.utc), ADMIN_USER_ID))
        connection.execute("""
            CREATE TABLE IF NOT EXISTS administrative_logs (
                id BIGSERIAL PRIMARY KEY,
                actor VARCHAR(64) NOT NULL,
                action VARCHAR(80) NOT NULL,
                target VARCHAR(128),
                details TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


def init_credit_request_db():
    """Create the application-owned credit store without seeding borrower data."""
    with db_connection() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (data_schema.get(),))
        connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
            sql.Identifier(data_schema.get())
        ))
        connection.execute("""
            CREATE TABLE IF NOT EXISTS borrower (
                borrower_id BIGSERIAL PRIMARY KEY,
                borrower_name VARCHAR(160) NOT NULL CHECK (LENGTH(BTRIM(borrower_name)) >= 2)
            )
        """)
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS borrower_name_unique ON borrower (LOWER(BTRIM(borrower_name)))")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS credit_requests (
                credit_request_number VARCHAR(24) PRIMARY KEY,
                borrower_id BIGINT NOT NULL REFERENCES borrower (borrower_id),
                borrower_name VARCHAR(160) NOT NULL,
                industry VARCHAR(80) NOT NULL,
                exposure BIGINT NOT NULL CHECK (exposure >= 0),
                facility VARCHAR(80) NOT NULL,
                rating VARCHAR(12) NOT NULL,
                requested_amount BIGINT NOT NULL CHECK (requested_amount > 0),
                status VARCHAR(32) NOT NULL,
                compliance_score SMALLINT NOT NULL CHECK (compliance_score BETWEEN 0 AND 100)
            )
        """)
        connection.execute("ALTER TABLE credit_requests ADD COLUMN IF NOT EXISTS collateral_coverage NUMERIC(7,2) NOT NULL DEFAULT 0")
        connection.execute("ALTER TABLE credit_requests ADD COLUMN IF NOT EXISTS recommended_pricing_bps INTEGER NOT NULL DEFAULT 325")
        connection.execute("ALTER TABLE credit_requests ADD COLUMN IF NOT EXISTS recommended_tenor_years SMALLINT NOT NULL DEFAULT 7")
        connection.execute("ALTER TABLE credit_requests ADD COLUMN IF NOT EXISTS geography VARCHAR(80) NOT NULL DEFAULT 'Unknown'")
        connection.execute("""
            UPDATE credit_requests SET geography = CASE MOD(HASHTEXT(credit_request_number::text)::bigint + 2147483648, 10)
                WHEN 0 THEN 'US Northeast' WHEN 1 THEN 'US Southeast'
                WHEN 2 THEN 'US Midwest' WHEN 3 THEN 'US West' WHEN 4 THEN 'Canada'
                WHEN 5 THEN 'United Kingdom' WHEN 6 THEN 'Europe'
                WHEN 7 THEN 'Middle East & Africa' WHEN 8 THEN 'Asia Pacific'
                ELSE 'Latin America' END
            WHERE geography = 'Unknown' OR BTRIM(geography) = ''
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS borrower_exposure_history (
                exposure_record_id BIGSERIAL PRIMARY KEY,
                borrower_id BIGINT NOT NULL REFERENCES borrower (borrower_id),
                facility_reference VARCHAR(40) NOT NULL,
                facility_type VARCHAR(80) NOT NULL,
                reporting_month DATE NOT NULL,
                original_exposure BIGINT NOT NULL CHECK (original_exposure > 0),
                scheduled_payment BIGINT NOT NULL CHECK (scheduled_payment >= 0),
                actual_payment BIGINT NOT NULL CHECK (actual_payment >= 0),
                outstanding_exposure BIGINT NOT NULL CHECK (outstanding_exposure >= 0),
                days_past_due SMALLINT NOT NULL DEFAULT 0 CHECK (days_past_due >= 0),
                payment_status VARCHAR(24) NOT NULL
                    CHECK (payment_status IN ('Current', 'Delayed', 'Defaulted')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (borrower_id, facility_reference, reporting_month)
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS borrower_exposure_history_lookup_idx
            ON borrower_exposure_history
                (borrower_id, facility_reference, reporting_month DESC, exposure_record_id DESC)
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS approval_authority_rules (
                rule_order SMALLINT PRIMARY KEY,
                maximum_post_approval_exposure BIGINT,
                authority_name VARCHAR(80) NOT NULL,
                authority_rank SMALLINT NOT NULL UNIQUE
            )
        """)
        connection.execute("""
            INSERT INTO approval_authority_rules
                (rule_order, maximum_post_approval_exposure, authority_name, authority_rank)
            VALUES
                (1, 25000000, 'Credit Officer', 1),
                (2, 75000000, 'Senior Credit Officer', 2),
                (3, 150000000, 'Credit Committee', 3),
                (4, NULL, 'Executive Committee', 4)
            ON CONFLICT (rule_order) DO NOTHING
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS credit_request_policy_evaluations (
                evaluation_id BIGSERIAL PRIMARY KEY,
                credit_request_number VARCHAR(24) NOT NULL
                    REFERENCES credit_requests (credit_request_number) ON DELETE CASCADE,
                clause_code VARCHAR(40) NOT NULL,
                clause_name VARCHAR(160) NOT NULL,
                result VARCHAR(12) NOT NULL CHECK (result IN ('PASS', 'WARNING', 'FAIL'))
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS credit_request_compliance (
                credit_request_number VARCHAR(24) PRIMARY KEY
                    REFERENCES credit_requests (credit_request_number) ON DELETE CASCADE,
                geography_risk VARCHAR(12) NOT NULL CHECK (geography_risk IN ('Low', 'Medium', 'High')),
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
                evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS policy_ai_configuration (
                id SMALLINT PRIMARY KEY CHECK (id = 1),
                mistral_library_id TEXT,
                mistral_agent_id TEXT,
                mistral_compliance_agent_id TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute(
            "ALTER TABLE policy_ai_configuration "
            "ADD COLUMN IF NOT EXISTS mistral_compliance_agent_id TEXT"
        )
        connection.execute(
            "ALTER TABLE policy_ai_configuration "
            "ADD COLUMN IF NOT EXISTS mistral_portfolio_agent_id TEXT"
        )
        connection.execute("""
            CREATE TABLE IF NOT EXISTS ai_compliance_reviews (
                review_id BIGSERIAL PRIMARY KEY,
                credit_request_number VARCHAR(24) NOT NULL
                    REFERENCES credit_requests (credit_request_number) ON DELETE CASCADE,
                agent_id TEXT NOT NULL,
                review JSONB NOT NULL,
                created_by VARCHAR(64) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS ai_compliance_reviews_request_created_idx
            ON ai_compliance_reviews (credit_request_number, created_at DESC, review_id DESC)
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS credit_request_exceptions (
                exception_id VARCHAR(24) PRIMARY KEY,
                credit_request_number VARCHAR(24) NOT NULL REFERENCES credit_requests (credit_request_number) ON DELETE CASCADE,
                exception_type VARCHAR(80) NOT NULL, clause_code VARCHAR(40) NOT NULL, severity VARCHAR(16) NOT NULL,
                exposure BIGINT NOT NULL, owner VARCHAR(120) NOT NULL, due_date DATE NOT NULL, status VARCHAR(32) NOT NULL,
                description TEXT NOT NULL, rationale JSONB NOT NULL, workflow JSONB NOT NULL, history JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            UPDATE credit_requests cr
            SET collateral_coverage = ROUND(cc.adjusted_collateral * 100.0 / cc.post_approval_exposure, 2)
            FROM credit_request_compliance cc
            WHERE cc.credit_request_number = cr.credit_request_number
              AND cr.collateral_coverage = 0
              AND cc.post_approval_exposure > 0
        """)
        connection.execute("""
            ALTER TABLE credit_request_exceptions
            DROP CONSTRAINT IF EXISTS credit_request_exceptions_credit_request_number_key
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS credit_request_exceptions_request_idx
            ON credit_request_exceptions (credit_request_number, created_at DESC)
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS policy_documents (
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
                page_count INTEGER NOT NULL CHECK (page_count >= 10),
                file_name VARCHAR(255) NOT NULL UNIQUE,
                local_pdf_path TEXT NOT NULL,
                mistral_document_id TEXT NOT NULL UNIQUE,
                mistral_library_id TEXT NOT NULL,
                mistral_agent_id TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS policy_category VARCHAR(100)")
        connection.execute("ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS parent_policy VARCHAR(100)")
        connection.execute("ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS clause_number VARCHAR(16)")
        connection.execute("ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS display_order SMALLINT")
        connection.execute("ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS document_format VARCHAR(16) NOT NULL DEFAULT 'PDF'")
        connection.execute("ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS source_type VARCHAR(16) NOT NULL DEFAULT 'manufactured'")
        connection.execute("ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS policy_type VARCHAR(40)")
        connection.execute("ALTER TABLE policy_documents ADD COLUMN IF NOT EXISTS library_policy_id VARCHAR(16)")
        connection.execute("""
            WITH known_types(policy_type, type_number) AS (
                VALUES
                    ('Leverage', 1), ('Collateral', 2), ('Pricing', 3), ('Tenor', 4),
                    ('Covenant', 5), ('Sector', 6), ('Delegation', 7), ('Rating', 8),
                    ('Country', 9), ('Industry', 10), ('LTV', 11), ('DSCR', 12),
                    ('Concentration', 13), ('Currency', 14), ('Duration', 15),
                    ('Liquidity', 16), ('Regulatory Capital', 17), ('Risk Appetite', 18),
                    ('Special Assets & Recovery', 19), ('Underwriting', 20)
            ), unknown_types AS (
                SELECT policy_type, 20 + DENSE_RANK() OVER (ORDER BY policy_type) AS type_number
                FROM (
                    SELECT DISTINCT policy_type
                    FROM policy_documents
                    WHERE policy_type IS NOT NULL
                      AND policy_type NOT IN (SELECT policy_type FROM known_types)
                ) types
            ), all_types AS (
                SELECT * FROM known_types
                UNION ALL
                SELECT * FROM unknown_types
            ), numbered AS (
                SELECT document.policy_id,
                       CONCAT(types.type_number, '.', ROW_NUMBER() OVER (
                           PARTITION BY document.policy_type
                           ORDER BY document.display_order, document.policy_id
                       )) AS library_policy_id
                FROM policy_documents document
                JOIN all_types types ON types.policy_type = document.policy_type
            )
            UPDATE policy_documents document
            SET library_policy_id = numbered.library_policy_id
            FROM numbered
            WHERE document.policy_id = numbered.policy_id
        """)
        connection.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS policy_documents_library_id_unique
            ON policy_documents (library_policy_id)
            WHERE library_policy_id IS NOT NULL
        """)
        connection.execute("ALTER TABLE policy_documents DROP CONSTRAINT IF EXISTS policy_documents_page_count_check")
        connection.execute("""
            DO $$ BEGIN
                ALTER TABLE policy_documents
                ADD CONSTRAINT policy_documents_page_count_positive CHECK (page_count > 0);
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS policy_generation_jobs (
                job_id VARCHAR(32) PRIMARY KEY,
                status VARCHAR(16) NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
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
            "ALTER TABLE policy_generation_jobs ALTER COLUMN total_documents SET DEFAULT 35"
        )
        connection.execute("""
            CREATE TABLE IF NOT EXISTS policy_controls (
                control_id VARCHAR(40) PRIMARY KEY,
                policy_id BIGINT NOT NULL
                    REFERENCES policy_documents (policy_id) ON DELETE CASCADE,
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
                status VARCHAR(32) NOT NULL
                    CONSTRAINT policy_controls_status_allowed
                    CHECK (status IN ('Effective', 'Needs Improvement', 'Ineffective')),
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
            ON policy_controls (policy_id, control_sequence)
        """)
        connection.execute(
            "ALTER TABLE policy_controls ADD COLUMN IF NOT EXISTS control_description TEXT"
        )
        connection.execute("""
            UPDATE policy_controls
            SET status = CASE
                WHEN effectiveness >= 85 THEN 'Effective'
                WHEN effectiveness >= 75 THEN 'Needs Improvement'
                ELSE 'Ineffective'
            END,
            control_description = COALESCE(
                control_description,
                CONCAT(control_name, ' verifies the requirements of ', policy_name,
                       ' for clause ', clause_number, '. The control records evidence, identifies ',
                       'exceptions, and routes unresolved findings to ', control_owner, '.')
            )
        """)
        connection.execute(
            "ALTER TABLE policy_controls ALTER COLUMN control_description SET NOT NULL"
        )
        connection.execute("""
            DO $$ BEGIN
                ALTER TABLE policy_controls
                ADD CONSTRAINT policy_controls_status_allowed
                CHECK (status IN ('Effective', 'Needs Improvement', 'Ineffective'));
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS policy_relationships (
                relationship_id BIGSERIAL PRIMARY KEY,
                policy_id BIGINT NOT NULL
                    REFERENCES policy_documents (policy_id) ON DELETE CASCADE,
                related_policy_id BIGINT NOT NULL
                    REFERENCES policy_documents (policy_id) ON DELETE CASCADE,
                relationship_type VARCHAR(40) NOT NULL,
                relationship_strength SMALLINT NOT NULL
                    CHECK (relationship_strength BETWEEN 1 AND 100),
                rationale TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK (policy_id < related_policy_id),
                UNIQUE (policy_id, related_policy_id)
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS policy_relationships_related_idx
            ON policy_relationships (related_policy_id, policy_id)
        """)
        connection.execute("""
            UPDATE policy_generation_jobs
            SET status = 'failed', message = 'Generation interrupted by a backend restart',
                error = 'Restart the generation job to continue with missing policies.',
                finished_at = CURRENT_TIMESTAMP
            WHERE status IN ('queued', 'running')
        """)

        connection.execute("""
            CREATE OR REPLACE VIEW latest_borrower_exposure AS
            SELECT DISTINCT ON (borrower_id, facility_reference)
                borrower_id, facility_reference, outstanding_exposure
            FROM borrower_exposure_history
            ORDER BY borrower_id, facility_reference, reporting_month DESC, exposure_record_id DESC
        """)


def resolve_borrower(connection, name: str, borrower_id: int | None = None) -> int:
    name = name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Borrower name must contain at least two characters")
    if borrower_id is not None:
        row = connection.execute("SELECT borrower_id FROM borrower WHERE borrower_id = %s AND LOWER(BTRIM(borrower_name)) = LOWER(%s)", (borrower_id, name)).fetchone()
        if not row:
            raise HTTPException(status_code=422, detail="Borrower ID and name do not match")
        return row["borrower_id"]
    return connection.execute("""
        INSERT INTO borrower (borrower_name) VALUES (%s)
        ON CONFLICT (user_id, LOWER(BTRIM(borrower_name))) DO UPDATE
        SET borrower_name = borrower.borrower_name
        RETURNING borrower_id
    """, (name,)).fetchone()["borrower_id"]



