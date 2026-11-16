-- Graph-compiled documentary requirements join numeric inventory rules.
CREATE OR REPLACE FUNCTION credit_data.is_supported_policy_rule(d jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
    SELECT credit_data.is_quantitative_rule(d) OR COALESCE(
        d->>'representation_version'='policy-representation-v1'
        AND d->>'rule_type'='documentary'
        AND d->'threshold_value'='true'::jsonb
        AND d->>'operator'='equals'
        AND d->'calculation_logic'->>'method'='document_presence',false)
$$;
