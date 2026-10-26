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
