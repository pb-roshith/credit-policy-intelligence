CREATE TABLE IF NOT EXISTS credit_data.policy_controls (
    control_id VARCHAR(40) PRIMARY KEY,
    policy_id BIGINT NOT NULL
        REFERENCES credit_data.policy_documents (policy_id) ON DELETE CASCADE,
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
);

CREATE INDEX IF NOT EXISTS policy_controls_policy_idx
ON credit_data.policy_controls (policy_id, control_sequence);
