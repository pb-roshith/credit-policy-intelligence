ALTER TABLE credit_data.rule_inventory_jobs ADD COLUMN IF NOT EXISTS discovered_documents JSONB NOT NULL DEFAULT '[]';
ALTER TABLE credit_data.rule_inventory_jobs ADD COLUMN IF NOT EXISTS review_progress JSONB NOT NULL DEFAULT '{}';
CREATE TABLE IF NOT EXISTS credit_data.inventory_batch_attempts (
 id BIGSERIAL PRIMARY KEY, job_id UUID REFERENCES credit_data.rule_inventory_jobs(id),
 policy_version_id BIGINT NOT NULL REFERENCES credit_data.policy_versions(id),
 batch_key TEXT NOT NULL, clause_ids JSONB NOT NULL, status TEXT NOT NULL,
 attempt INTEGER NOT NULL, error_code TEXT, error_details TEXT, retry_status TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS inventory_attempts_job ON credit_data.inventory_batch_attempts(job_id);
CREATE TABLE IF NOT EXISTS credit_data.rule_quality_reports (
 id BIGSERIAL PRIMARY KEY, job_id UUID REFERENCES credit_data.rule_inventory_jobs(id),
 rule_version_id BIGINT NOT NULL REFERENCES credit_data.policy_rule_versions(id),
 definition_checksum TEXT NOT NULL, prompt_version TEXT NOT NULL,
 execution_id UUID REFERENCES credit_data.agent_execution_logs(id),
 status TEXT NOT NULL, report JSONB, error_code TEXT, retry_status TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(rule_version_id,definition_checksum,prompt_version)
);
