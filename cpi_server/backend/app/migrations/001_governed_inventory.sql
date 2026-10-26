-- Applied transactionally by bootstrap; repeatable on existing deployments.
CREATE TABLE IF NOT EXISTS credit_data.inventory_policies (
    id BIGINT PRIMARY KEY REFERENCES credit_data.policy_documents(policy_id),
    code TEXT NOT NULL UNIQUE, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credit_data.policy_versions (
    id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL REFERENCES credit_data.inventory_policies(id),
    version TEXT NOT NULL, effective_date DATE, effective_date_source TEXT,
    checksum TEXT NOT NULL, is_current BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(policy_id,version,checksum), UNIQUE(id,policy_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS current_inventory_policy_version
    ON credit_data.policy_versions(policy_id) WHERE is_current;
CREATE TABLE IF NOT EXISTS credit_data.inventory_documents (
    id BIGSERIAL PRIMARY KEY,
    policy_version_id BIGINT NOT NULL UNIQUE REFERENCES credit_data.policy_versions(id),
    source_document_id BIGINT NOT NULL REFERENCES credit_data.policy_documents(policy_id),
    file_name TEXT NOT NULL, file_type TEXT NOT NULL, checksum TEXT NOT NULL,
    ingestion_status TEXT NOT NULL CHECK(ingestion_status IN ('Pending','Completed','Failed')),
    extraction_status TEXT NOT NULL DEFAULT 'Pending' CHECK(extraction_status IN ('Pending','Running','Completed','Failed')),
    ingested_at TIMESTAMPTZ, processed_at TIMESTAMPTZ, error TEXT,
    UNIQUE(id,policy_version_id)
);
CREATE TABLE IF NOT EXISTS credit_data.policy_clauses (
    id BIGSERIAL PRIMARY KEY,
    policy_version_id BIGINT NOT NULL REFERENCES credit_data.policy_versions(id),
    document_id BIGINT NOT NULL REFERENCES credit_data.inventory_documents(id),
    sequence INTEGER NOT NULL, section_heading TEXT, clause_number TEXT,
    page_number INTEGER, source_excerpt TEXT NOT NULL CHECK(length(source_excerpt)>0),
    checksum TEXT NOT NULL,
    UNIQUE(document_id,sequence), UNIQUE(id,policy_version_id),
    FOREIGN KEY(document_id,policy_version_id) REFERENCES credit_data.inventory_documents(id,policy_version_id)
);
CREATE TABLE IF NOT EXISTS credit_data.policy_rule_entities (
    id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL REFERENCES credit_data.inventory_policies(id),
    rule_code TEXT NOT NULL UNIQUE, rule_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id,policy_id)
);
ALTER TABLE credit_data.policy_rule_versions ADD COLUMN IF NOT EXISTS rule_entity_id BIGINT REFERENCES credit_data.policy_rule_entities(id);
ALTER TABLE credit_data.policy_rule_versions ADD COLUMN IF NOT EXISTS policy_version_id BIGINT REFERENCES credit_data.policy_versions(id);
ALTER TABLE credit_data.policy_rule_versions ADD COLUMN IF NOT EXISTS clause_id BIGINT REFERENCES credit_data.policy_clauses(id);
ALTER TABLE credit_data.policy_rule_versions ADD COLUMN IF NOT EXISTS superseded_version_id BIGINT REFERENCES credit_data.policy_rule_versions(id);
ALTER TABLE credit_data.policy_rule_versions ADD COLUMN IF NOT EXISTS reviewed_by TEXT;
ALTER TABLE credit_data.policy_rule_versions ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE credit_data.policy_rule_versions ADD COLUMN IF NOT EXISTS review_comments TEXT;
ALTER TABLE credit_data.policy_rule_versions ADD COLUMN IF NOT EXISTS approval_decision TEXT;
ALTER TABLE credit_data.policy_rule_versions ADD COLUMN IF NOT EXISTS extraction_key TEXT UNIQUE;
ALTER TABLE credit_data.policy_rule_versions DROP CONSTRAINT IF EXISTS policy_rules_status_check;
ALTER TABLE credit_data.policy_rule_versions DROP CONSTRAINT IF EXISTS policy_rule_versions_status_check;
ALTER TABLE credit_data.policy_rule_versions ADD CONSTRAINT policy_rule_versions_status_check
    CHECK(status IN ('Draft','Under Review','Approved','Active','Inactive','Rejected','Retired'));
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='rule_version_policy_link') THEN
        ALTER TABLE credit_data.policy_rule_versions ADD CONSTRAINT rule_version_policy_link
            FOREIGN KEY(policy_version_id,policy_id) REFERENCES credit_data.policy_versions(id,policy_id);
        ALTER TABLE credit_data.policy_rule_versions ADD CONSTRAINT rule_version_entity_link
            FOREIGN KEY(rule_entity_id,policy_id) REFERENCES credit_data.policy_rule_entities(id,policy_id);
        ALTER TABLE credit_data.policy_rule_versions ADD CONSTRAINT rule_version_clause_link
            FOREIGN KEY(clause_id,policy_version_id) REFERENCES credit_data.policy_clauses(id,policy_version_id);
    END IF;
END $$;
-- Preserve explicitly activated legacy versions. Approval will no longer activate.
UPDATE credit_data.policy_rule_versions SET status='Active' WHERE status='Approved' AND active;
CREATE OR REPLACE VIEW credit_data.policy_rules AS SELECT * FROM credit_data.policy_rule_versions;
CREATE TABLE IF NOT EXISTS credit_data.rule_applicability_conditions (
    id BIGSERIAL PRIMARY KEY, rule_version_id BIGINT NOT NULL REFERENCES credit_data.policy_rule_versions(id),
    sequence INTEGER NOT NULL, condition JSONB NOT NULL,
    UNIQUE(rule_version_id,sequence)
);
CREATE TABLE IF NOT EXISTS credit_data.rule_input_requirements (
    id BIGSERIAL PRIMARY KEY, rule_version_id BIGINT NOT NULL REFERENCES credit_data.policy_rule_versions(id),
    field_name TEXT NOT NULL, data_source TEXT, required BOOLEAN NOT NULL DEFAULT true,
    UNIQUE(rule_version_id,field_name)
);
CREATE TABLE IF NOT EXISTS credit_data.rule_evidence_requirements (
    id BIGSERIAL PRIMARY KEY, rule_version_id BIGINT NOT NULL REFERENCES credit_data.policy_rule_versions(id),
    evidence_key TEXT NOT NULL, description TEXT NOT NULL, requirement_type TEXT NOT NULL,
    UNIQUE(rule_version_id,evidence_key)
);
CREATE TABLE IF NOT EXISTS credit_data.rule_relationships (
    id BIGSERIAL PRIMARY KEY,
    rule_version_id BIGINT NOT NULL REFERENCES credit_data.policy_rule_versions(id),
    related_rule_version_id BIGINT NOT NULL REFERENCES credit_data.policy_rule_versions(id),
    relationship_type TEXT NOT NULL CHECK(relationship_type IN ('AND','OR','Duplicate candidate','Similar')),
    reason TEXT NOT NULL,
    CHECK(rule_version_id<>related_rule_version_id),
    UNIQUE(rule_version_id,related_rule_version_id,relationship_type)
);
CREATE TABLE IF NOT EXISTS credit_data.rule_reviews (
    id BIGSERIAL PRIMARY KEY, rule_version_id BIGINT NOT NULL REFERENCES credit_data.policy_rule_versions(id),
    reviewed_by TEXT NOT NULL, decision TEXT NOT NULL, comments TEXT NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS credit_data.audit_events (
    id BIGSERIAL PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
    previous_value JSONB, new_value JSONB NOT NULL, action TEXT NOT NULL,
    actor TEXT NOT NULL, reason TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS credit_data.rule_inventory_jobs (
    id UUID PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('Queued','Running','Completed','Completed with errors','Failed')),
    policy_ids JSONB NOT NULL, created_by TEXT NOT NULL, report JSONB NOT NULL DEFAULT '{}',
    progress JSONB NOT NULL DEFAULT '[]', error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, heartbeat_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS one_inventory_job ON credit_data.rule_inventory_jobs((true)) WHERE status IN ('Queued','Running');
CREATE TABLE IF NOT EXISTS credit_data.agent_execution_logs (
    id UUID PRIMARY KEY, job_id UUID REFERENCES credit_data.rule_inventory_jobs(id),
    policy_version_id BIGINT REFERENCES credit_data.policy_versions(id),
    agent_name TEXT NOT NULL, model_name TEXT NOT NULL, prompt_version TEXT NOT NULL,
    status TEXT NOT NULL, attempt INTEGER NOT NULL, error_code TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS "user".rule_assessment_runs (
    id BIGSERIAL, user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id',true),''),
    review_id BIGINT NOT NULL, request_id VARCHAR(64) NOT NULL, workflow_stage TEXT,
    engine_version TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id,id), UNIQUE(user_id,review_id),
    FOREIGN KEY(user_id,review_id) REFERENCES "user".ai_compliance_reviews(user_id,review_id)
);
CREATE TABLE IF NOT EXISTS "user".policy_request_mappings (
    id BIGSERIAL, user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id',true),''),
    run_id BIGINT NOT NULL, request_id VARCHAR(64) NOT NULL,
    policy_id BIGINT NOT NULL REFERENCES credit_data.inventory_policies(id),
    policy_version_id BIGINT NOT NULL REFERENCES credit_data.policy_versions(id),
    applicability TEXT NOT NULL, reason TEXT NOT NULL,
    PRIMARY KEY(user_id,id), UNIQUE(user_id,run_id,policy_version_id),
    FOREIGN KEY(user_id,run_id) REFERENCES "user".rule_assessment_runs(user_id,id),
    FOREIGN KEY(policy_version_id,policy_id) REFERENCES credit_data.policy_versions(id,policy_id)
);
CREATE TABLE IF NOT EXISTS "user".request_rule_assessments (
    id BIGSERIAL, user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id',true),''),
    run_id BIGINT NOT NULL, request_id VARCHAR(64) NOT NULL,
    rule_version_id BIGINT NOT NULL REFERENCES credit_data.policy_rule_versions(id),
    policy_version_id BIGINT NOT NULL REFERENCES credit_data.policy_versions(id),
    policy_id BIGINT NOT NULL REFERENCES credit_data.inventory_policies(id),
    rule_id BIGINT NOT NULL REFERENCES credit_data.policy_rule_entities(id),
    clause_id BIGINT NOT NULL REFERENCES credit_data.policy_clauses(id),
    workflow_stage TEXT, applicability TEXT NOT NULL,
    input_values JSONB NOT NULL, expected_threshold JSONB, formula JSONB,
    observed_value JSONB, variance TEXT, result TEXT NOT NULL,
    severity TEXT, evidence_references JSONB NOT NULL, missing_inputs JSONB NOT NULL,
    explanation TEXT NOT NULL, evaluated_at TIMESTAMPTZ NOT NULL, engine_version TEXT NOT NULL,
    PRIMARY KEY(user_id,id), FOREIGN KEY(user_id,run_id) REFERENCES "user".rule_assessment_runs(user_id,id),
    UNIQUE(user_id,run_id,rule_version_id),
    CHECK(result IN ('Pass','Warning','Breach','Not Applicable','Unable to Assess','Manual Review Required'))
);
CREATE TABLE IF NOT EXISTS "user".assessment_evidence (
    id BIGSERIAL, user_id VARCHAR(64) NOT NULL DEFAULT NULLIF(current_setting('app.user_id',true),''),
    assessment_id BIGINT NOT NULL, evidence_key TEXT NOT NULL, source TEXT NOT NULL,
    observed_value JSONB, source_reference TEXT, conflicting BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY(user_id,id), FOREIGN KEY(user_id,assessment_id) REFERENCES "user".request_rule_assessments(user_id,id)
);
CREATE TABLE IF NOT EXISTS credit_data.rule_extraction_batches (
    id BIGSERIAL PRIMARY KEY, policy_version_id BIGINT NOT NULL REFERENCES credit_data.policy_versions(id),
    batch_key TEXT NOT NULL UNIQUE, rule_ids JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE credit_data.inventory_documents ADD COLUMN IF NOT EXISTS source_path TEXT;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='rule_version_exact_identity') THEN
        ALTER TABLE credit_data.policy_rule_versions ADD CONSTRAINT rule_version_exact_identity UNIQUE(id,rule_entity_id,policy_version_id,clause_id,policy_id);
        ALTER TABLE "user".request_rule_assessments ADD CONSTRAINT assessment_exact_rule_link
            FOREIGN KEY(rule_version_id,rule_id,policy_version_id,clause_id,policy_id)
            REFERENCES credit_data.policy_rule_versions(id,rule_entity_id,policy_version_id,clause_id,policy_id);
    END IF;
END $$;
ALTER TABLE credit_data.inventory_documents ADD COLUMN IF NOT EXISTS stated_metadata JSONB NOT NULL DEFAULT '{}';
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='rule_activation_state') THEN
        ALTER TABLE credit_data.policy_rule_versions ADD CONSTRAINT rule_activation_state CHECK(active=(status='Active'));
        ALTER TABLE credit_data.policy_rule_versions ADD CONSTRAINT active_rule_has_approval CHECK(status<>'Active' OR (approved_by IS NOT NULL AND approval_date IS NOT NULL));
    END IF;
END $$;
CREATE TABLE IF NOT EXISTS credit_data.policy_extraction_reports (
    id UUID PRIMARY KEY REFERENCES credit_data.agent_execution_logs(id),
    policy_version_id BIGINT NOT NULL REFERENCES credit_data.policy_versions(id),
    source_document_id BIGINT NOT NULL REFERENCES credit_data.inventory_documents(id),
    schema_version TEXT NOT NULL,
    output JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(source_document_id,policy_version_id) REFERENCES credit_data.inventory_documents(id,policy_version_id)
);
CREATE INDEX IF NOT EXISTS policy_extraction_report_version_idx ON credit_data.policy_extraction_reports(policy_version_id,created_at DESC);
ALTER TABLE credit_data.rule_input_requirements ADD COLUMN IF NOT EXISTS field_definition TEXT;
ALTER TABLE credit_data.rule_input_requirements ADD COLUMN IF NOT EXISTS field_unit TEXT;
