"""Illustrative inputs for demonstration requests and policy assessments."""

from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
import re

from ..services.rule_engine import MISSING, compare, field_value, referenced_fields

ACTUAL_GENERATOR_VERSION = 'demonstration-actual-v2'


def manufacture_observed_actual(request_id, rule, evaluation, as_of=None):
    """Supply the displayed metric even when no executable calculation is mapped.

    This is a rule-level sample in threshold units, not a claimed calculation
    from supporting financials. Keep compliance/manual decisions intact and
    record the sample's threshold comparison separately.
    """
    if evaluation.get('observed_value') is not None:
        return evaluation, None
    from ..services.credit_data import fact
    from decimal import InvalidOperation

    as_of = as_of or date.today()
    from ..services.assessment_comparison import comparison_definition
    definition = comparison_definition(rule['definition'])
    threshold = definition.get('threshold_value')
    op = definition.get('operator')
    seed = sha256(f'{request_id}:rule:{rule["id"]}'.encode()).digest()[0]
    factor = 0.8 if seed % 2 == 0 else 1.2
    if op == 'between':
        threshold = [definition.get('lower_bound'), definition.get('upper_bound')]
        if all(isinstance(value, (int, float)) for value in threshold):
            lower, upper = threshold
            actual = (lower + upper) / 2 if seed % 2 == 0 else upper + max(abs(upper) * .2, 1)
        else:
            actual = 100
    elif isinstance(threshold, bool):
        actual = threshold if seed % 2 == 0 else not threshold
    elif isinstance(threshold, (int, float)):
        actual = round(threshold * factor, 6) if threshold else (-1 if seed % 2 == 0 else 1)
    elif isinstance(threshold, list):
        actual = threshold[0] if threshold else 'Sample value'
    elif threshold is not None:
        actual = threshold
    elif op in ('exists', 'does_not_exist'):
        actual = True
    else:
        actual = 100
    try:
        matched = compare(actual, op, threshold) if op else None
    except (ValueError, TypeError, KeyError, InvalidOperation):
        matched = None
    key = f'demonstration_actual.rule_{rule["id"]}'
    unit = definition.get('threshold_unit')
    source = fact(request_id, key, actual, unit, as_of=as_of.isoformat(),
        source_identifier=f'{ACTUAL_GENERATOR_VERSION}:{request_id}:{rule["id"]}',
        extraction_method='rule-level demonstration actual in policy threshold units')
    result = deepcopy(evaluation)
    result['observed_value'] = actual
    result['calculation_performed'] = 'Manufactured Demonstration Data: sampled actual in policy threshold units'
    result['input_values'][key] = actual
    result['threshold_comparison'] = {'actual': actual, 'operator': op, 'threshold': threshold,
        'unit': unit, 'condition_met': matched,
        'status': 'Condition met' if matched is True else 'Condition not met' if matched is False else 'Comparison needs policy mapping',
        'source_type': 'SYNTHETIC'}
    try:
        result['variance'] = str(float(actual) - float(threshold))
    except (TypeError, ValueError):
        result['variance'] = None
    return result, {'attribute_name': key, 'rule_field': key, **source}


def manufacture_assessment_inputs(request_id, proposal, rules, as_of=None):
    """Fill missing inputs once per request; never change scope or policy thresholds.

    Values are stable for a request/field and shared by rules using that field.
    The returned data belongs to the assessment snapshot, not the source request.
    """
    as_of = as_of or date.today()
    data = deepcopy(proposal)
    generated = {}
    data['evidence'] = deepcopy(data.get('evidence') or [])

    def put(field, value):
        if not field or field in scope_fields or field_value(data, field) is not MISSING:
            return
        node = data
        parts = field.split('.')
        for part in parts[:-1]:
            if part in node and not isinstance(node[part], dict):
                return
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        generated[field] = value

    def sample(field, threshold):
        if isinstance(threshold, bool):
            return threshold
        if isinstance(threshold, (int, float)):
            variation = sha256(f'{request_id}:{field}'.encode()).digest()[0] % 2
            return round(float(threshold) * (0.8 if variation == 0 else 1.2), 6)
        if isinstance(threshold, list):
            return threshold[0] if threshold else 'Sample value'
        return threshold if threshold is not None else 100

    def conditions(condition):
        if not condition:
            return
        if condition.get('field'):
            put(condition['field'], sample(condition['field'], condition.get('value')))
        for key in ('all', 'any'):
            for child in condition.get(key) or []:
                conditions(child)

    scope_fields = set()
    def collect_scope(condition):
        if not condition:
            return
        if condition.get('field'):
            scope_fields.add(condition['field'])
        for key in ('all', 'any'):
            for child in condition.get(key) or []:
                collect_scope(child)
    for rule in rules:
        collect_scope(rule['definition'].get('applicability_conditions'))
    scope_fields.update(('status', 'currency'))

    for rule in rules:
        d = rule['definition']
        logic = d.get('calculation_logic') or {}
        method = logic.get('method')
        unit = d.get('threshold_unit') or ''
        field = logic.get('field')
        threshold = d.get('threshold_value')
        if d.get('operator') == 'between':
            lower, upper = d.get('lower_bound'), d.get('upper_bound')
            if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
                threshold = (lower + upper) / 2
        desired = sample(field or logic.get('numerator') or str(rule['id']), threshold)
        if method == 'direct':
            if d.get('operator') in ('exists', 'does_not_exist'):
                desired = True
            if isinstance(desired, (int, float)) and not isinstance(desired, bool):
                for magnitude, multiplier in (('billion', 10**9), ('million', 10**6), ('thousand', 1000)):
                    if re.search(r'\b' + magnitude + r's?\b', unit, re.I):
                        desired *= multiplier
                        break
            put(field, desired)
        elif method in ('ratio', 'percentage'):
            numerator, denominator = logic['numerator'], logic['denominator']
            ratio = float(desired) if isinstance(desired, (int, float)) else 1.5
            if method == 'percentage' or unit.strip().lower() in ('%', 'percent', 'percentage'):
                ratio /= 100
            left, right = field_value(data, numerator), field_value(data, denominator)
            put(denominator, float(left) / ratio if left is not MISSING and isinstance(left, (int, float)) and ratio else 100)
            right = field_value(data, denominator)
            put(numerator, ratio * float(right) if isinstance(right, (int, float)) else ratio * 100)
        elif method == 'date_age':
            put(logic.get('as_of_field'), as_of.isoformat())
            end = field_value(data, logic['as_of_field']) if logic.get('as_of_field') else as_of.isoformat()
            days = float(desired) if isinstance(desired, (int, float)) else 30
            if unit.lower() in ('month', 'months'):
                days *= 30
            elif unit.lower() in ('year', 'years'):
                days *= 365
            days = max(0, min(round(days), 36500))
            try:
                end_date = date.fromisoformat(str(end)[:10])
            except ValueError:
                end_date = as_of
            put(field, (end_date - timedelta(days=days)).isoformat())
        elif method == 'compound':
            conditions(logic.get('condition'))
        elif method == 'document_presence':
            put('documents', {})
            documents = data.get('documents')
            key = logic['document_key']
            if isinstance(documents, dict) and key not in documents:
                documents[key] = {'present': True, 'source_type': 'SYNTHETIC'}
                generated['documents'] = deepcopy(documents)
        # Applicability attributes are never manufactured to force a rule into scope.
        for key in referenced_fields(d):
            if key in (d.get('input_data_fields') or []) and key not in scope_fields:
                put(key, 100)
        for requirement in d.get('evidence_requirements') or []:
            key = requirement['key']
            if requirement['type'] == 'data':
                put(key, 100)
            elif requirement['type'] in ('document', 'approval') and not any(e.get('key') == key for e in data['evidence']):
                data['evidence'].append({'key': key, 'source': 'Manufactured Demonstration Data',
                    'source_type': 'SYNTHETIC', 'reference': f'synthetic:{request_id}:{key}',
                    'value': {'present': True, 'demonstration_only': True}})
    return data, generated


def supplement_actual_resolution(rule, resolution, data, generated, as_of):
    """Attach manufactured facts to canonical resolution without losing real lineage."""
    from ..services.credit_data import canonical_name, fact
    from ..services.rule_engine import execute_rule

    if resolution.get('instances') or resolution['resolution_status'] == 'CONFLICTING':
        return resolution
    fields = set(referenced_fields(rule['definition']))
    fields.update(e['key'] for e in rule['definition'].get('evidence_requirements', []))
    supplied = {key: value for key, value in generated.items()
                if key in fields and field_value(resolution['engine_data'], key) is MISSING}
    existing_keys = {item.get('key') for item in resolution['evidence']}
    evidence_keys = {item['key'] for item in rule['definition'].get('evidence_requirements', [])}
    evidence = [item for item in data['evidence'] if item.get('source_type') == 'SYNTHETIC'
                and item.get('key') in evidence_keys and item.get('key') not in existing_keys]
    if not supplied and not evidence:
        return resolution
    result = deepcopy(resolution)
    engine_data = result['engine_data']
    for field, value in supplied.items():
        node = engine_data
        parts = field.split('.')
        for key in parts[:-1]:
            node = node.setdefault(key, {})
        node[parts[-1]] = deepcopy(value)
        name = canonical_name(field)
        item = fact(result['request_id'], name, value, as_of=as_of.isoformat(),
                    source_identifier=f'synthetic:{result["request_id"]}:{field}')
        result['resolved_fields'].append({'attribute_name': name, 'rule_field': field, **item})
        result['provenance'].append(item['provenance'])
        result['missing_fields'] = [key for key in result['missing_fields'] if key != name]
    engine_data['evidence'] = result['evidence'] + evidence
    result['evidence'] = engine_data['evidence']
    for item in evidence:
        result['missing_fields'] = [key for key in result['missing_fields'] if key != 'documentation.' + item['key']]
    result['evaluation'] = execute_rule(rule['definition'], engine_data, as_of)
    if result['missing_fields'] and result['evaluation']['result'] not in ('Not Applicable', 'Manual Review Required'):
        result['evaluation'].update(result='Unable to Assess', severity=None,
            missing_inputs=sorted(set(result['missing_fields'] + result['evaluation']['missing_inputs'])))
    result['actual_value'] = result['evaluation']['observed_value']
    result['resolution_status'] = 'PARTIAL' if result['missing_fields'] else 'COMPLETE'
    result['actual_provenance'] = fact(result['request_id'], 'assessment.observed_value',
        result['actual_value'], result['unit'], 'DERIVED', as_of.isoformat(),
        source_identifier='policy-rule-engine:' + str(rule['id']),
        extraction_method='deterministic evaluation', inputs=deepcopy(result['provenance']),
        verification_status='CALCULATED')['provenance']
    return result
def sample_financials(requested_amount, exposure):
    debt=float(exposure)+float(requested_amount)
    ebitda=round(debt/3.5,2)
    debt_service=round(ebitda/1.6,2)
    return {'total_debt':debt,'ebitda':ebitda,'annual_debt_service':debt_service,
            'debt_service':debt_service,'net_operating_income':ebitda,
            'leverage_ratio':3.5,'dscr':1.6,'debt_service_coverage_ratio':1.6,
            'ltv':65.0,'loan_to_value':65.0,'collateral_value':round(debt/0.65,2)}
