-- Rules require no approval lifecycle. Keep legacy columns for historical compatibility.
ALTER TABLE credit_data.policy_rule_versions DROP CONSTRAINT IF EXISTS active_rule_has_approval;
ALTER TABLE credit_data.policy_rule_versions ALTER COLUMN status SET DEFAULT 'Active';
ALTER TABLE credit_data.policy_rule_versions ALTER COLUMN active SET DEFAULT true;
UPDATE credit_data.policy_rule_versions SET status='Active',active=true WHERE status<>'Active' OR NOT active;
