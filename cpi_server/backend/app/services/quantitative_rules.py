"""The inventory contains only explicitly numeric policy requirements."""
import math


def is_quantitative_rule(definition):
    if definition.get('rule_type', '').lower() != 'quantitative':
        return False
    values = []
    for name in ('threshold_value', 'lower_bound', 'upper_bound'):
        value = definition.get(name)
        values.extend(value if isinstance(value, list) else [value])
    return any(isinstance(value, (int, float)) and not isinstance(value, bool)
               and math.isfinite(value) for value in values)


def is_supported_inventory_rule(definition):
    if is_quantitative_rule(definition): return True
    return (definition.get('representation_version')=='policy-representation-v1'
            and definition.get('rule_type')=='documentary'
            and definition.get('threshold_value') is True
            and definition.get('operator')=='equals'
            and (definition.get('calculation_logic') or {}).get('method')=='document_presence')
