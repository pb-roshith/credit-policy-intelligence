-- One-time, explicitly requested reset of borrower data. Users and policy rules are retained.
BEGIN;
CREATE TABLE IF NOT EXISTS credit_data.borrower (
    borrower_id BIGSERIAL PRIMARY KEY,
    borrower_name VARCHAR(160) NOT NULL CHECK (LENGTH(BTRIM(borrower_name)) >= 2)
);
CREATE UNIQUE INDEX IF NOT EXISTS borrower_name_unique ON credit_data.borrower (LOWER(BTRIM(borrower_name)));
TRUNCATE credit_data.borrower_financial_history, credit_data.borrower_exposure_history,
    credit_data.credit_request_policy_evaluations,
    credit_data.credit_request_compliance,
    credit_data.credit_requests, credit_data.borrower RESTART IDENTITY;
ALTER TABLE credit_data.credit_requests ADD COLUMN IF NOT EXISTS borrower_id BIGINT NOT NULL REFERENCES credit_data.borrower (borrower_id);
ALTER TABLE credit_data.borrower_exposure_history DROP COLUMN IF EXISTS credit_request_number;
ALTER TABLE credit_data.borrower_exposure_history DROP COLUMN IF EXISTS borrower_name;
ALTER TABLE credit_data.borrower_exposure_history ADD COLUMN IF NOT EXISTS borrower_id BIGINT NOT NULL REFERENCES credit_data.borrower (borrower_id);
CREATE UNIQUE INDEX IF NOT EXISTS borrower_history_month_unique ON credit_data.borrower_exposure_history (borrower_id, facility_reference, reporting_month);
ALTER TABLE credit_data.borrower_financial_history DROP COLUMN IF EXISTS credit_request_number;
ALTER TABLE credit_data.borrower_financial_history DROP COLUMN IF EXISTS borrower_name;
ALTER TABLE credit_data.borrower_financial_history ADD COLUMN IF NOT EXISTS borrower_id BIGINT NOT NULL REFERENCES credit_data.borrower (borrower_id);
COMMIT;
