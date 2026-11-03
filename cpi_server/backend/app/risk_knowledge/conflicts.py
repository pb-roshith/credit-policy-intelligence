"""Conservative overlap discovery. Flags are findings for review, never precedence."""
from itertools import combinations
from .evaluation import leaves, number


def disjoint(a, b):
    # Only prove disjointness for flat AND expressions. Other cases remain potential overlaps.
    if a.conditions.logic != 'AND' or b.conditions.logic != 'AND' or a.conditions.groups or b.conditions.groups:
        return False
    constraints = a.scope + leaves(a.conditions) + b.scope + leaves(b.conditions)
    by_attribute = {}
    for c in constraints:
        by_attribute.setdefault(c.attribute, []).append(c)
    for conditions in by_attribute.values():
        equals = [c.value for c in conditions if c.operator == '=']
        if equals and any(v != equals[0] for v in equals):
            return True
        allowed = [set(c.value) for c in conditions if c.operator == 'in' and isinstance(c.value, list)]
        if equals and any(equals[0] not in s for s in allowed):
            return True
        if allowed and not set.intersection(*allowed):
            return True
        # Distinct currencies are incomparable rather than proven disjoint.
        if len({c.unit for c in conditions if c.unit}) > 1:
            continue
        try:
            lower = [(number(c.value), c.operator == '>=') for c in conditions if c.operator in ('>', '>=')]
            upper = [(number(c.value), c.operator == '<=') for c in conditions if c.operator in ('<', '<=')]
            for lo, inclusive_lo in lower:
                for hi, inclusive_hi in upper:
                    if lo > hi or lo == hi and not (inclusive_lo and inclusive_hi):
                        return True
        except (ValueError, TypeError, ArithmeticError):
            pass
    return False


def discover_conflicts(rules):
    findings = []
    active = [r for r in rules if r.status == 'APPROVED']
    for a, b in combinations(active, 2):
        if a.risk_domain != b.risk_domain or disjoint(a, b):
            continue
        same_conditions = a.scope == b.scope and a.conditions == b.conditions and a.exceptions == b.exceptions
        same_outcome = a.outcome == b.outcome
        if same_conditions and same_outcome:
            kind = 'DUPLICATE'
        elif a.outcome.action == b.outcome.action and a.outcome.authority != b.outcome.authority:
            kind = 'POTENTIAL_POLICY_CONFLICT'
        elif a.outcome.action == b.outcome.action:
            kind = 'OVERLAPPING_RULES'
        else:
            continue
        findings.append({'finding_id': a.rule_id + ':' + b.rule_id, 'kind': kind,
                         'rules': [a.rule_id, b.rule_id], 'names': [a.rule_name, b.rule_name],
                         'reason': 'Scopes and condition ranges may overlap' + (' with different approval authorities.' if kind == 'POTENTIAL_POLICY_CONFLICT' else '.'),
                         'status': 'REQUIRES_REVIEW', 'precedence': 'UNKNOWN',
                         'sources': [a.policy.model_dump(), b.policy.model_dump()]})
    for r in rules:
        if r.status == 'SUPERSEDED':
            findings.append({'finding_id': 'superseded:' + r.rule_id, 'kind': 'SUPERSEDED_RULE',
                             'rules': [r.rule_id], 'names': [r.rule_name], 'reason': 'Excluded by reviewed superseded status.',
                             'status': 'INFORMATIONAL', 'precedence': 'No successor assumed', 'sources': [r.policy.model_dump()]})
    return findings
