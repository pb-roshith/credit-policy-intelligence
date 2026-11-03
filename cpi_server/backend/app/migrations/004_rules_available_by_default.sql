-- Rules require no approval lifecycle. Keep legacy columns for historical compatibility.
ALTER TABLE credit_data.policy_rule_versions DROP CONSTRAINT IF EXISTS active_rule_has_approval;
ALTER TABLE credit_data.policy_rule_versions ALTER COLUMN status SET DEFAULT 'Active';
ALTER TABLE credit_data.policy_rule_versions ALTER COLUMN active SET DEFAULT true;
-- Preserve the established behavior for legacy rules. Risk Knowledge extraction
-- candidates explicitly require review and must survive application restarts.
UPDATE credit_data.policy_rule_versions AS existing SET status='Active',active=true
WHERE (status<>'Active' OR NOT active)
  AND COALESCE(extraction_key,'') NOT LIKE 'risk-knowledge:%'
  AND NOT EXISTS (SELECT 1 FROM credit_data.policy_rule_versions candidate
                  WHERE candidate.rule_key=existing.rule_key
                    AND candidate.extraction_key LIKE 'risk-knowledge:%');
