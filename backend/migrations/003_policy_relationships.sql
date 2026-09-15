CREATE TABLE IF NOT EXISTS credit_data.policy_relationships (
    relationship_id BIGSERIAL PRIMARY KEY,
    policy_id BIGINT NOT NULL
        REFERENCES credit_data.policy_documents (policy_id) ON DELETE CASCADE,
    related_policy_id BIGINT NOT NULL
        REFERENCES credit_data.policy_documents (policy_id) ON DELETE CASCADE,
    relationship_type VARCHAR(40) NOT NULL,
    relationship_strength SMALLINT NOT NULL
        CHECK (relationship_strength BETWEEN 1 AND 100),
    rationale TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (policy_id < related_policy_id),
    UNIQUE (policy_id, related_policy_id)
);

CREATE INDEX IF NOT EXISTS policy_relationships_related_idx
ON credit_data.policy_relationships (related_policy_id, policy_id);
