"""Recover explicit comparisons for demonstration findings from their policy text.

Source rule versions remain unchanged. A numeric threshold alone never implies
a maximum: recover the direction from the rule's question or quoted condition.
"""
from copy import deepcopy
from decimal import InvalidOperation
import re

from .rule_engine import compare
from .rule_expectation import expected_condition

NUMBER = r'[-+]?\d[\d,]*(?:\.\d+)?'
PREFIX = r'(?:USD|INR|EUR|GBP|JPY|CAD|AUD|CHF|CNY|AED|SGD|HKD)?\s*'
SCALE = r'(?:%|percent|million|billion|thousand)?'
RANGE = re.compile(r'(?:between|from|ranges?\s+from)\s+' + PREFIX +
    r'(?P<lower>' + NUMBER + r')\s*' + SCALE + r'\s*(?:and|to)\s*' + PREFIX +
    r'(?P<upper>' + NUMBER + r')', re.I)
PHRASES = [
    ('less_than_or_equal', r'no\s+more\s+than|at\s+or\s+below|not\s+(?:exceed|exceeding)|up\s+to|within|maximum(?:\s+of)?|capped\s+at'),
    ('greater_than_or_equal', r'no\s+less\s+than|at\s+least|at\s+or\s+above|minimum(?:\s+of)?'),
    ('greater_than', r'greater\s+than|more\s+than|exceed(?:s|ing)?|above'),
    ('less_than', r'less\s+than|below'),
    ('equals', r'equal\s+to|set\s+at'),
]


def comparison_definition(definition):
    result = deepcopy(definition)
    texts = [definition.get(key) or '' for key in
             ('check_question', 'rule_description', 'threshold_source', 'source_excerpt')]
    if not result.get('operator'):
        lower, upper = result.get('lower_bound'), result.get('upper_bound')
        if lower is not None and upper is not None:
            result['operator'] = 'between'
        else:
            for text in texts:
                if result.get('threshold_value') is None:
                    match = RANGE.search(text)
                    if match:
                        result.update(operator='between',
                            lower_bound=float(match['lower'].replace(',', '')),
                            upper_bound=float(match['upper'].replace(',', '')))
                        if not result.get('threshold_unit'):
                            currency = re.search(r'\b(USD|INR|EUR|GBP)\b', match[0], re.I)
                            scale = re.search(r'\b(million|billion|thousand)\b', match[0], re.I)
                            result['threshold_unit'] = ' '.join(v[0] for v in (currency, scale) if v) or None
                        break
                candidates = []
                for op, phrase in PHRASES:
                    for match in re.finditer(r'\b(?:' + phrase + r')\s+' + PREFIX + r'(' + NUMBER + r')', text, re.I):
                        threshold = result.get('threshold_value')
                        if isinstance(threshold, (int, float)) and float(match[1].replace(',', '')) == threshold:
                            candidates.append(op)
                # Longer phrases match before substrings such as "more than".
                if candidates:
                    result['operator'] = candidates[0]
                    break
        if result.get('operator'):
            result['comparison_mapping_source'] = 'Explicit comparison in policy rule text'
    # A dual-review/approval trigger calls for review when the condition holds;
    # it is not a requirement to keep the observed value above the trigger.
    text = ' '.join(texts[:2]).lower()
    if not result.get('threshold_type') and result.get('operator') in ('greater_than', 'greater_than_or_equal'):
        if re.search(r'\b(requir\w*|must)\b.{0,120}\b(review\w*|approv\w*)\b', text):
            result['threshold_type'] = 'WARNING_TRIGGER'
    return result


def refresh_finding_comparisons(review):
    """Refresh display metadata for both newly run and previously saved reviews."""
    result = deepcopy(review)
    if result.get('assessment_scope') == 'current-semantic-graph':
        return result  # Semantic outcomes/units are already frozen graph results.
    definitions = {str(rule['id']): rule['definition'] for rule in result.get('rule_snapshots', [])}
    for finding in result.get('findings', []):
        original = definitions.get(str(finding.get('rule_version_id')))
        if not original:
            continue
        definition = comparison_definition(original)
        actual = finding.get('observed_value')
        comparison = finding.get('threshold_comparison') or {}
        if actual is None:
            continue
        threshold = [definition.get('lower_bound'), definition.get('upper_bound')] if definition.get('operator') == 'between' else definition.get('threshold_value')
        # Only add comparison metadata for the manufactured, threshold-unit
        # metrics. Existing deterministic engine outcomes remain authoritative.
        if comparison or 'SYNTHETIC' in finding.get('actual_sources', []):
            try:
                met = compare(actual, definition.get('operator'), threshold) if definition.get('operator') else None
            except (ValueError, TypeError, InvalidOperation, KeyError):
                met = None
            finding['threshold_comparison'] = {**comparison, 'actual': actual,
                'operator': definition.get('operator'), 'threshold': threshold,
                'unit': definition.get('threshold_unit'), 'condition_met': met,
                'status': 'Condition met' if met is True else 'Condition not met' if met is False else 'Comparison needs policy mapping',
                'mapping_source': definition.get('comparison_mapping_source') or 'Policy rule definition'}
        finding['operator'] = definition.get('operator')
        finding['threshold_type'] = definition.get('threshold_type')
        finding['expected_condition'] = expected_condition(definition)
        finding['threshold'] = finding['expected_condition']
        if not finding.get('actual_unit'):
            finding['actual_unit'] = definition.get('threshold_unit')
    return result
