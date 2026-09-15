ALTER TABLE credit_data.policy_documents
ADD COLUMN IF NOT EXISTS library_policy_id VARCHAR(16);

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
        FROM credit_data.policy_documents
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
    FROM credit_data.policy_documents document
    JOIN all_types types ON types.policy_type = document.policy_type
)
UPDATE credit_data.policy_documents document
SET library_policy_id = numbered.library_policy_id
FROM numbered
WHERE document.policy_id = numbered.policy_id;

CREATE UNIQUE INDEX IF NOT EXISTS policy_documents_library_id_unique
ON credit_data.policy_documents (library_policy_id)
WHERE library_policy_id IS NOT NULL;

ALTER TABLE credit_data.policy_controls
ADD COLUMN IF NOT EXISTS control_description TEXT;

UPDATE credit_data.policy_controls
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
    );

ALTER TABLE credit_data.policy_controls
ALTER COLUMN control_description SET NOT NULL;

DO $$ BEGIN
    ALTER TABLE credit_data.policy_controls
    ADD CONSTRAINT policy_controls_status_allowed
    CHECK (status IN ('Effective', 'Needs Improvement', 'Ineffective'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
