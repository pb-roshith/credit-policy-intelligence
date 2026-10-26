"""Display source-backed expected conditions without inventing numeric thresholds."""
import json

OPERATORS={'equals':'=','not_equals':'!=','greater_than':'>','greater_than_or_equal':'>=',
           'less_than':'<','less_than_or_equal':'<=','in_list':'one of','not_in_list':'not one of'}

def display_value(value):
    if value is True:return 'Yes'
    if value is False:return 'No'
    if isinstance(value,(dict,list)):return json.dumps(value,ensure_ascii=False)
    return str(value)

def expected_condition(definition):
    operator=definition.get('operator')
    threshold=definition.get('threshold_value')
    unit=definition.get('threshold_unit') or ''
    if operator=='between' and definition.get('lower_bound') is not None and definition.get('upper_bound') is not None:
        return f"Between {display_value(definition['lower_bound'])} and {display_value(definition['upper_bound'])} {unit}".strip()
    if threshold is not None:
        return f"{OPERATORS.get(operator,operator or '')} {display_value(threshold)} {unit}".strip()
    if operator in ('exists','does_not_exist'):
        return 'Must be present' if operator=='exists' else 'Must be absent'
    # Keep a qualitative policy requirement visible. This is not an executable
    # substitute for a missing extracted numeric limit or calculation.
    for field in ('check_question','rule_description','source_excerpt'):
        requirement=definition.get(field)
        if requirement and requirement.strip():return requirement.strip()
    return 'Source requirement missing; rule correction required'
