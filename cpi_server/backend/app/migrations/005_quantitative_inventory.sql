-- Preserve historical assessment foreign keys while excluding nonnumeric requirements.
CREATE OR REPLACE FUNCTION credit_data.is_quantitative_rule(d jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
    SELECT COALESCE(d->>'rule_type' = 'quantitative' AND (
        jsonb_typeof(d->'threshold_value') = 'number'
        OR jsonb_typeof(d->'lower_bound') = 'number'
        OR jsonb_typeof(d->'upper_bound') = 'number'
        OR EXISTS (SELECT 1 FROM jsonb_array_elements(
            CASE WHEN jsonb_typeof(d->'threshold_value') = 'array'
                 THEN d->'threshold_value' ELSE '[]'::jsonb END) v
            WHERE jsonb_typeof(v) = 'number')
    ), false)
$$;
UPDATE credit_data.policy_rule_versions SET active=false,status='Retired'
WHERE NOT credit_data.is_quantitative_rule(definition) AND (active OR status<>'Retired');
