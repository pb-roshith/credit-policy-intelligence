from .evaluation import leaves, number


def validate_rule(rule, taxonomy, clause):
    conditions = rule.scope + leaves(rule.conditions) + [c for e in rule.exceptions for c in leaves(e)]
    def complete_expression(expression, allow_empty=False):
        return (allow_empty or bool(expression.conditions or expression.groups)) and all(complete_expression(g) for g in expression.groups)
    def valid_value(c):
        field = taxonomy.field(c.attribute)
        if not field or field.concept_id != c.taxonomy_mapping:
            return False
        try:
            values = c.value if c.operator in ('in', 'not_in') else [c.value]
            if not isinstance(values, list) or not values:
                return False
            if c.operator == 'exists':
                return True
            if field.data_type in ('decimal', 'integer'):
                return all(number(v).is_finite() for v in values) and (c.attribute != 'amount' or c.unit is not None)
            if field.data_type == 'boolean':
                return all(isinstance(v, bool) for v in values) and c.operator in ('=', '!=')
            if field.data_type == 'ordered_enum' and c.operator in ('>', '<', '>=', '<='):
                return field.metadata.get('rating_order') == 'worst_to_best' and all(v in field.allowed_values for v in values)
            if c.operator not in ('=', '!=', 'in', 'not_in'):
                return False
            return all(isinstance(v, (str, int, float, bool)) and (not field.allowed_values or v in field.allowed_values) for v in values)
        except (ValueError, TypeError, ArithmeticError):
            return False
    exact_source = clause is not None and rule.policy.passage == clause['raw_text'] and rule.policy.document_id == clause['document_id'] and rule.policy.model_dump(exclude={'provider'}) == {k: v for k, v in clause['source'].items() if k != 'provider'}
    has_exception_text = any(term in rule.policy.passage.lower() for term in ('except ', 'unless '))
    return {
        'source_provenance_verified': exact_source,
        'taxonomy_bindings_approved': bool(conditions) and all(taxonomy.field(c.attribute) is not None and taxonomy.field(c.attribute).concept_id == c.taxonomy_mapping for c in conditions),
        'operators_and_values_valid': bool(conditions) and all(valid_value(c) for c in conditions),
        'outcome_resolved': rule.outcome.action not in ('', 'UNKNOWN'),
        'approval_authority_resolved': 'approval' not in rule.outcome.action.lower() or bool(rule.outcome.authority and rule.outcome.authority != 'UNKNOWN'),
        'exception_representation_present': not has_exception_text or bool(rule.exceptions),
        'expression_groups_complete': complete_expression(rule.conditions, allow_empty=bool(rule.scope)) and all(complete_expression(e) for e in rule.exceptions),
        'structured_conditions_present': bool(leaves(rule.conditions)) or bool(rule.scope),
        'source_clause_complete': len(rule.policy.passage.strip()) > 10,
    }
