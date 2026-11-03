-- Risk knowledge extends the existing CPI store; no additional database/server.
CREATE TABLE IF NOT EXISTS credit_data.risk_knowledge_objects (
    kind TEXT NOT NULL,
    owner_id TEXT NOT NULL DEFAULT '',
    id TEXT NOT NULL,
    payload JSONB NOT NULL,
    position BIGSERIAL NOT NULL,
    PRIMARY KEY(kind, owner_id, id)
);
CREATE INDEX IF NOT EXISTS risk_knowledge_kind_order
    ON credit_data.risk_knowledge_objects(kind, owner_id, position);
