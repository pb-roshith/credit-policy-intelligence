"""Deterministic, three-valued evaluation; approved taxonomy controls rating semantics."""
import operator
from datetime import date
from decimal import Decimal, InvalidOperation
from .models import CreditRequest, Expression, Rule

MISSING = object()
OPS = {'=': operator.eq, '!=': operator.ne, '>': operator.gt, '>=': operator.ge,
       '<': operator.lt, '<=': operator.le}


def number(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not an amount')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Number must be finite')
    return result


def leaves(expression):
    return expression.conditions + [c for g in expression.groups for c in leaves(g)]


def combine(results, logic):
    if logic == 'AND':
        return False if False in results else None if None in results else True
    return True if True in results else None if None in results else False


def evaluate_condition(condition, request, taxonomy):
    actual = request.attributes.get(condition.attribute, MISSING)
    evidence = {'attribute': condition.attribute, 'original_term': condition.original_term,
                'normalized_term': condition.normalized_term, 'operator': condition.operator,
                'expected': condition.value, 'actual': None if actual is MISSING else actual,
                'unit': condition.unit, 'taxonomy_mapping': condition.taxonomy_mapping,
                'result': None, 'reason': ''}
    field = taxonomy.field(condition.attribute)
    if actual is MISSING or actual is None or actual == '':
        evidence['reason'] = 'Required attribute is missing'
        return evidence
    if not field or field.concept_id != condition.taxonomy_mapping:
        evidence['reason'] = 'No unique approved taxonomy binding'
        return evidence
    expected = condition.value
    actual, normalization = taxonomy.normalize(condition.attribute, actual)
    evidence['normalized_actual'] = actual
    if normalization:
        evidence['normalization'] = normalization
    try:
        if condition.unit and request.currency != condition.unit:
            raise ValueError('Currency/unit mismatch; no implicit conversion')
        if condition.operator == 'exists':
            value = True
        elif field.data_type == 'ordered_enum' and condition.operator in ('>', '>=', '<', '<='):
            if field.metadata.get('rating_order') != 'worst_to_best':
                raise ValueError('No approved rating ordering')
            scale = field.allowed_values
            if actual not in scale or expected not in scale:
                raise ValueError('Rating is absent from the approved scale')
            value = OPS[condition.operator](scale.index(actual), scale.index(expected))
            evidence['rating_scale'] = scale
        else:
            if field.data_type in ('decimal', 'integer'):
                actual = number(actual)
                expected = [number(v) for v in expected] if condition.operator in ('in', 'not_in') else number(expected)
            elif field.data_type == 'boolean':
                if not isinstance(actual, bool) or not isinstance(expected, bool):
                    raise ValueError('Boolean attribute requires true or false')
            elif field.allowed_values:
                if actual not in field.allowed_values:
                    raise ValueError('Value is not in the approved vocabulary')
            if condition.operator in ('in', 'not_in'):
                if not isinstance(expected, list):
                    raise ValueError('Membership requires a list')
                value = actual in expected
                if condition.operator == 'not_in':
                    value = not value
            elif condition.operator in OPS:
                value = OPS[condition.operator](actual, expected)
            else:
                raise ValueError('Unsupported operator')
        evidence['result'] = value
        evidence['reason'] = f"{evidence.get('normalized_actual')} {condition.operator} {condition.value}" + (f' {condition.unit}' if condition.unit else '')
    except (ValueError, TypeError, InvalidOperation) as error:
        evidence['reason'] = str(error)
    return evidence


def evaluate_expression(expression, request, taxonomy):
    checks = [evaluate_condition(c, request, taxonomy) for c in expression.conditions]
    groups = [evaluate_expression(g, request, taxonomy) for g in expression.groups]
    values = [c['result'] for c in checks] + [g['result'] for g in groups]
    result = combine(values, expression.logic)
    return {'logic': expression.logic, 'result': result, 'checks': checks, 'groups': groups}


def evaluate_rule(rule, request, taxonomy):
    rule = Rule.model_validate(rule) if isinstance(rule, dict) else rule
    request = CreditRequest.model_validate(request) if isinstance(request, dict) else request
    date.fromisoformat(request.as_of)
    result = {'rule_id': rule.rule_id, 'rule_name': rule.rule_name, 'outcome': rule.outcome.model_dump(),
              'policy': rule.policy.model_dump(), 'synthetic': rule.synthetic,
              'rule_status': rule.status, 'status': 'EXCLUDED', 'reason': '', 'scope': None,
              'conditions': None, 'exceptions': [], 'graph_path': [], 'potential_conflicts': []}
    if rule.status != 'APPROVED':
        result['reason'] = 'Only approved rules enter formal evaluation'
        return result
    if not rule.validation or not all(rule.validation.values()) or rule.requires_review:
        result.update(status='INSUFFICIENT_DATA', reason='Approved rule has unresolved validation checks')
        return result
    if rule.policy.effective_date and date.fromisoformat(request.as_of) < date.fromisoformat(rule.policy.effective_date):
        result.update(status='NOT_APPLICABLE', reason='Request predates the explicit policy effective date')
        return result
    scope = evaluate_expression(Expression(conditions=rule.scope), request, taxonomy)
    condition = evaluate_expression(rule.conditions, request, taxonomy)
    base = combine([scope['result'], condition['result']], 'AND')
    exceptions = [evaluate_expression(e, request, taxonomy) for e in rule.exceptions]
    result.update(scope=scope, conditions=condition, exceptions=exceptions)
    if base is False:
        result.update(status='NOT_APPLICABLE', reason='At least one necessary scope or condition does not match')
    elif base is None:
        result.update(status='INSUFFICIENT_DATA', reason='Required input or approved taxonomy semantics are unavailable')
    elif any(e['result'] is True for e in exceptions):
        result.update(status='NOT_APPLICABLE', reason='An explicit policy exception matches')
    elif any(e['result'] is None for e in exceptions):
        result.update(status='INSUFFICIENT_DATA', reason='An exception cannot be resolved from the supplied attributes')
    else:
        result.update(status='APPLICABLE', reason=rule.outcome.action + (': ' + rule.outcome.authority if rule.outcome.authority else ': ' + str(rule.outcome.value or 'See source clause')))
    result['graph_path'] = [
        {'from': request.borrower, 'predicate': 'REQUESTS', 'to': str(request.attributes.get('product', 'UNKNOWN'))},
        {'from': str(request.attributes.get('product', 'UNKNOWN')), 'predicate': 'HAS_EXPOSURE', 'to': f"{request.currency} {request.attributes.get('amount', 'UNKNOWN')}"},
        {'from': f"{request.currency} {request.attributes.get('amount', 'UNKNOWN')}", 'predicate': 'EVALUATED_AGAINST', 'to': rule.rule_id},
        {'from': rule.rule_id, 'predicate': 'HAS_OUTCOME', 'to': rule.outcome.authority or rule.outcome.action},
        {'from': rule.rule_id, 'predicate': 'DERIVED_FROM', 'to': rule.clause_id}]
    return result
