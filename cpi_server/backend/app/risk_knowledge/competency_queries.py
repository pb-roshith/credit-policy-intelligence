"""Trace competency questions through the published graph and policy history."""
from collections import Counter
from datetime import date
from typing import Literal

from .competency_projection import candidate_relationships, comparisons
from .semantic_bindings import attribute_definition, SCOPE_TERMS

Question = Literal['borrower', 'industry', 'geography', 'product', 'rating', 'exposure', 'collateral',
                   'breach_approval', 'exceptions', 'policy_class', 'effective', 'coverage', 'relationship']

CONCERNS = {'rating': 'RATING_DEPENDENCY', 'exposure': 'EXPOSURE_LIMIT',
            'collateral': 'COLLATERAL_REQUIREMENT', 'exceptions': 'EXCEPTION_PROVISION'}
SCOPE_PREDICATES = {
    'industry': {'APPLIES_TO_INDUSTRY', 'APPLIES_TO_SUBSECTOR', 'APPLIES_TO_INDUSTRY_TIER'},
    'geography': {'APPLIES_IN'},
    'product': {'APPLIES_TO_PRODUCT', 'DOCUMENTS_PRODUCT_SCOPE'},
}


def source_details(matcher, refs):
    details = []
    for ref in refs:
        node = matcher.nodes[ref]
        properties = node['properties']
        if node['type'] == 'SourcePassage':
            details.append({'node_id': ref, 'clause': properties.get('clause_reference'), 'page': properties.get('page'),
                            'quote': properties['text']})
    return details


def rule_answer(matcher, rid):
    record, row = matcher.rows[rid]
    rule = row['extracted']
    version = matcher.targets(rid, 'PART_OF_VERSION')[0]
    period_ids = matcher.targets(rid, 'HAS_EFFECTIVE_PERIOD') or matcher.targets(version, 'HAS_EFFECTIVE_PERIOD')
    approvals = []
    for aid in dict.fromkeys(matcher.targets(rid, 'REQUIRES_APPROVAL') + matcher.targets(rid, 'REQUIRES_APPROVAL_ON_BREACH')
                             + matcher.targets(rid, 'REQUIRES_APPROVAL_ABOVE_THRESHOLD')):
        approvals.append({'triggered_by_breach': aid in matcher.targets(rid, 'REQUIRES_APPROVAL_ON_BREACH'),
                          'above_threshold': aid in matcher.targets(rid, 'REQUIRES_APPROVAL_ABOVE_THRESHOLD'),
                          'authorities': [matcher.nodes[f]['label'] for f in matcher.targets(aid, 'REQUIRES_APPROVAL_FROM')],
                          'requirement': matcher.nodes[aid]['properties']})
    return {'id': rid, 'label': rule['name'], 'policy_id': record['policy_id'], 'policy': record['policy_name'],
            'version': record['policy_version'], 'policy_version_id': record['policy_version_id'],
            'source_rule_code': matcher.nodes[rid]['properties'].get('source_rule_code'),
            'synthetic': record['synthetic'], 'source_quote': rule['source_quote'],
            'conditions': rule.get('conditions'), 'thresholds': rule['thresholds'],
            'approvals': approvals, 'evidence_requirements': rule['evidence_requirements'],
            'exception_ids': matcher.targets(rid, 'HAS_EXCEPTION'),
            'policy_classes': [matcher.nodes[tid]['label'] for tid in matcher.targets(rid, 'CLASSIFIED_AS')],
            'derived_from_classes': [matcher.nodes[tid]['label'] for tid in matcher.targets(rid, 'DERIVED_FROM_POLICY_CLASS')],
            'effective_periods': [matcher.nodes[pid]['properties'] for pid in period_ids],
            'sources': source_details(matcher, matcher.nodes[rid]['source_refs'])}


def coverage(matcher):
    """Surface recurring unmapped fields as review candidates with citations."""
    pending = Counter()
    examples = {}
    source_candidates = Counter()
    source_examples = {}
    for record in matcher.records:
        for clause in record['source_clauses']:
            for label, quote in candidate_relationships(clause['source_excerpt']):
                source_candidates[label] += 1
                source_examples.setdefault(label, {'policy': record['policy_name'], 'version': record['policy_version'],
                    'clause_id': clause['id'], 'quote': quote})
        for row in record['rules']:
            rule = row['extracted']
            for condition in comparisons(rule.get('conditions')):
                field = condition['field']
                if not attribute_definition(field) and field not in SCOPE_TERMS:
                    pending[field] += 1
                    examples.setdefault(field, {'policy': record['policy_name'], 'version': record['policy_version'],
                        'clause_id': rule['clause_id'], 'quote': condition.get('evidence') or rule['source_quote']})
    return {'policies': len(matcher.records),
            'source_passages': sum(len(r['source_clauses']) for r in matcher.records),
            'rules': len(matcher.rows),
            'published_rules': sum(n['type'] == 'PolicyRule' for n in matcher.nodes.values()),
            'scope_needs_review': [r['policy_name'] for r in matcher.records if (r.get('policy_scope') or {}).get('status') != 'APPROVED'],
            'scope_edge_counts': {predicate: sum(edge['predicate'] == predicate for edge in matcher.graph['relationships'])
                                  for predicate in sorted(set.union(*SCOPE_PREDICATES.values()))},
            'relationship_candidates': [{'field': field, 'count': count, **examples[field]} for field, count in pending.most_common()],
            'source_relationship_candidates': [{'label': label, 'count': count, **source_examples[label]}
                                               for label, count in source_candidates.most_common()]}


def answer(matcher, question, value='', *, request=None, policy_id=None, limit=25, offset=0):
    from ..services.semantic_matching import normalized

    if question == 'coverage':
        return coverage(matcher)
    if question == 'relationship':
        rows = [{'id': edge['subject'], 'label': matcher.nodes[edge['subject']]['label'],
                 'relationship': value, 'scope': matcher.nodes[edge['object']]['label'],
                 'scope_type': matcher.nodes[edge['object']]['type'],
                 'scope_sources': source_details(matcher, edge['source_refs'])}
                for edge in matcher.graph['relationships'] if edge['predicate'] == value]
        return {'question': question, 'results': rows[offset:offset + limit], 'total': len(rows),
                'next_offset': offset + limit if offset + limit < len(rows) else None}
    indices, rows = set(), []
    if question == 'borrower':
        decisions = [d for d in matcher.match(request or {})['decisions'] if d['candidate_type'] == 'Policy']
        rows = [d for d in decisions if d['applicability'] != 'Not Applicable' and (not policy_id or d['policy_id'] == policy_id)]
        rows.sort(key=lambda d: (d['applicability'] != 'Applicable', d['policy_name']))
    elif question in SCOPE_PREDICATES:
        owner_edges = matcher.graph['relationships']
        target_nodes = {
            'industry': {'Industry', 'IndustryTier', 'Subsector'}, 'geography': {'Geography', 'Country', 'Jurisdiction', 'Region'},
            'product': {'Product'},
        }[question]
        targets = {nid for nid, node in matcher.nodes.items() if node['type'] in target_nodes and
                   normalized(node['label'], question) == normalized(value, question)}
        versions = {r['policy_version_id']: r for r in matcher.records}
        inherited = []
        for edge in owner_edges:
            if edge['predicate'] not in SCOPE_PREDICATES[question] or edge['object'] not in targets:
                continue
            owner = edge['subject']
            if owner in matcher.rows:
                record, _ = matcher.rows[owner]
                row = rule_answer(matcher, owner)
            else:
                record = versions[int(owner.rsplit(':', 1)[-1])]
                row = {'id': owner, 'label': record['policy_name'], 'policy_id': record['policy_id'],
                       'policy': record['policy_name'], 'version': record['policy_version'],
                       'policy_version_id': record['policy_version_id'], 'synthetic': record['synthetic']}
            if policy_id and record['policy_id'] != policy_id:
                continue
            target = matcher.nodes[edge['object']]
            scoped = {'scope': target['label'], 'scope_type': target['type'], 'relationship': edge['predicate'],
                      'scope_sources': source_details(matcher, edge['source_refs'])}
            if question == 'product' and owner not in matcher.rows:
                for link in matcher.inc[owner]:
                    rid = link['subject']
                    if link['predicate'] != 'PART_OF_VERSION' or rid not in matcher.rows:
                        continue
                    explicit = set(matcher.targets(rid, 'APPLIES_TO_PRODUCT') + matcher.targets(rid, 'DOCUMENTS_PRODUCT_SCOPE'))
                    if not explicit:
                        inherited.append({**rule_answer(matcher, rid), **scoped, 'inherited_scope': True})
            else:
                rows.append({**row, **scoped})
        rows.extend(inherited)
        rows.sort(key=lambda row: (row['policy'], row.get('inherited_scope', False), row['label']))
    else:
        if question in CONCERNS:
            concerns = {nid for nid, node in matcher.nodes.items() if node['type'] == 'PolicyConcern'
                        and node['properties']['concern_code'] == CONCERNS[question]}
            indices = {e['subject'] for e in matcher.graph['relationships'] if e['predicate'] == 'CONCERNS' and e['object'] in concerns}
            if question == 'exceptions':
                indices.update(e['subject'] for e in matcher.graph['relationships'] if e['predicate'] == 'HAS_EXCEPTION')
        elif question == 'breach_approval':
            indices = {e['subject'] for e in matcher.graph['relationships'] if e['predicate'] in
                       ('REQUIRES_APPROVAL_ON_BREACH', 'REQUIRES_APPROVAL_ABOVE_THRESHOLD')}
        elif question == 'policy_class':
            indices = {value} if value in matcher.nodes and matcher.nodes[value]['type'] == 'PolicyRule' else set()
        for rid in indices:
            record = matcher.rows[rid][0]
            if policy_id and record['policy_id'] != policy_id:
                continue
            if value and question != 'policy_class' and value != rid:
                continue
            rows.append(rule_answer(matcher, rid))
        rows.sort(key=lambda row: (row['policy'], row['label'], row['id']))
    if request is not None and question != 'borrower':
        decisions = {row['graph_node_id']: row for row in matcher.match(request)['decisions']}
        rows = [{**row, 'applicability': decisions.get(row['id'], {}).get('applicability', 'Unable to Determine')}
                for row in rows if decisions.get(row['id'], {}).get('applicability') != 'Not Applicable']
    return {'question': question, 'results': rows[offset:offset + limit], 'total': len(rows),
            'next_offset': offset + limit if offset + limit < len(rows) else None,
            'match_basis': 'request_applicability' if question == 'borrower' else 'published_source_paths'}


def version_on(versions, on_date):
    eligible = [v for v in versions if v['effective_date'] and date.fromisoformat(str(v['effective_date'])) <= on_date]
    if not eligible:
        return None, 'No registered policy version has a known effective date at or before the requested date.'
    latest = max(str(v['effective_date']) for v in eligible)
    choices = [v for v in eligible if str(v['effective_date']) == latest]
    if len(choices) != 1 or any(not v['effective_date'] for v in versions):
        return None, 'Policy version dates are incomplete or overlap. The effective rule edition cannot be established.'
    return choices[0], None
