"""Business ontology contract, JSON transport schema and semantic validation.

This versioned design is independent of the operational rule compiler. Neither
schema validity nor a review status grants policy approval or execution rights.
"""
from copy import deepcopy
from datetime import date
from functools import lru_cache
import hashlib
import json
import math

VERSION = '1.2.0'
NAMESPACE = 'urn:cpi:ontology:credit-policy:'
SCHEMA_ID = 'urn:cpi:schema:credit-policy:1.2.0'
STATUSES = ['PROPOSED', 'APPROVED', 'REJECTED', 'SUPERSEDED']


def prop(kind='string', description='', **constraints):
    return {'type': kind, 'description': description, **constraints}


TEXT = prop(minLength=1)
DATE = prop(format='date')
CHECKSUM = prop(pattern='^[a-f0-9]{64}$')
ID = prop(format='uri', minLength=1)
VALUE = {'oneOf': [prop('string', minLength=1), prop('number'), prop('boolean'),
                   prop('array', items=TEXT, minItems=1, uniqueItems=True)]}


def cls(label, definition, properties=None, required=(), parent=None):
    return {'label': label, 'definition': definition, 'parent': parent,
            'properties': properties or {}, 'required_properties': list(required)}


CLASSES = {
    'Customer': cls('Customer', 'A person or organization with a banking relationship.',
        {'customer_reference': TEXT, 'customer_kind': prop(enum=['PERSON', 'ORGANIZATION'])}),
    'Borrower': cls('Borrower', 'A customer seeking or receiving credit; a specialized Customer.', parent='Customer'),
    'LoanApplication': cls('Loan application', 'A request for credit, distinct from an originated loan.',
        {'application_reference': TEXT, 'requested_amount': prop('number', minimum=0), 'currency': prop(pattern='^[A-Z]{3}$')}),
    'Loan': cls('Loan', 'An originated credit agreement or facility.',
        {'loan_reference': TEXT, 'currency': prop(pattern='^[A-Z]{3}$')}),
    'CreditPolicy': cls('Credit policy', 'A stable policy identity across separately identified versions.',
        {'policy_reference': TEXT, 'risk_domain': TEXT}, ['policy_reference']),
    'PolicyVersion': cls('Policy version', 'An immutable, source-bound version of a credit policy.',
        {'version': TEXT, 'source_checksum': CHECKSUM}, ['version', 'source_checksum']),
    'PolicySection': cls('Policy section', 'A section of one policy version, optionally nested within another section.',
        {'section_reference': TEXT}, ['section_reference']),
    'PolicyRule': cls('Policy rule', 'A source-derived normative requirement within exactly one policy version.',
        {'rule_reference': TEXT, 'rule_kind': prop(enum=['QUANTITATIVE', 'QUALITATIVE', 'EXCEPTION_RULE']),
         'requirement_text':prop(description='Exact operative source statement, including qualitative duties.',minLength=1)}, ['rule_reference', 'rule_kind']),
    'Condition': cls('Condition', 'A typed comparison used in scope, eligibility or exception logic.',
        {'field': TEXT, 'operator': prop(enum=['EQ', 'NE', 'GT', 'GTE', 'LT', 'LTE', 'IN', 'NOT_IN', 'EXISTS']), 'value': VALUE, 'unit': TEXT}, ['field', 'operator']),
    'ConditionGroup': cls('Condition group', 'An explicit AND, OR or NOT expression over conditions or nested groups.',
        {'logic': prop(enum=['AND', 'OR', 'NOT'])}, ['logic']),
    'Threshold': cls('Threshold', 'A numerical boundary with an operator and unit, measured against exactly one metric.',
        {'operator': prop(enum=['GT', 'GTE', 'LT', 'LTE', 'EQ', 'NE']), 'value': prop('number'), 'unit': TEXT}, ['operator', 'value', 'unit']),
    'CustomerSegment': cls('Customer segment', 'A controlled grouping of customers, such as SME; no numerical SME definition is assumed.',
        {'segment_code': TEXT}, ['segment_code']),
    'Product': cls('Product', 'A controlled credit product or facility type.', {'product_code': TEXT}, ['product_code']),
    'Geography': cls('Geography', 'A jurisdiction or geographic grouping used in explicit policy scope.',
        {'geography_code': TEXT, 'code_scheme': TEXT}, ['geography_code', 'code_scheme']),
    'RiskMetric': cls('Risk metric', 'A defined quantitative measure with declared permitted units and optional formula.',
        {'metric_key': TEXT, 'allowed_units': prop('array', items=TEXT, minItems=1, uniqueItems=True), 'formula': TEXT}, ['metric_key', 'allowed_units']),
    'Exception': cls('Exception', 'A conditional deviation from one base rule. Approval and alternative rules are explicit links.',
        {'exception_reference': TEXT, 'rationale': TEXT}, ['exception_reference']),
    'ApprovalRequirement': cls('Approval requirement', 'A required decision by an identified authority; this is not an approval already granted.',
        {'decision_type': prop(enum=['APPROVAL', 'ESCALATION', 'CONCURRENCE']), 'notes': TEXT}, ['decision_type']),
    'ApprovalAuthority': cls('Approval authority', 'An accountable role or committee empowered to make a specified decision.',
        {'authority_code': TEXT, 'authority_kind': prop(enum=['ROLE', 'COMMITTEE'])}, ['authority_code', 'authority_kind']),
    'EvidenceRequirement': cls('Evidence requirement', 'A required evidence type and optional freshness condition.',
        {'evidence_type': TEXT, 'maximum_age_days': prop('integer', minimum=0)}, ['evidence_type']),
    'ControlEvidence': cls('Control evidence', 'An actual evidence artifact with its recorded verification state.',
        {'evidence_reference': TEXT, 'evidence_type': TEXT, 'verification_state': prop(enum=['UNVERIFIED', 'VERIFIED', 'STALE']), 'collected_on': DATE},
        ['evidence_reference', 'evidence_type', 'verification_state']),
    'EffectivePeriod': cls('Effective period', 'An inclusive start date and optional inclusive end date; absent period means unknown validity.',
        {'start_date': DATE, 'end_date': DATE}, ['start_date']),
    'SourcePassage': cls('Source passage', 'Exact evidence text, source identity, version and checksum; never a generated policy summary.',
        {'document_reference': TEXT, 'version': TEXT, 'source_checksum': CHECKSUM, 'text': TEXT,
         'page': prop('integer', minimum=1), 'clause_reference': TEXT,
         'origin': prop(enum=['POLICY_SOURCE', 'ILLUSTRATIVE_EXAMPLE'])},
        ['document_reference', 'version', 'source_checksum', 'text', 'origin']),
    'TaxonomyConcept': cls('Taxonomy concept', 'A reference to a controlled classification concept; classification is distinct from executable applicability.',
        {'taxonomy_id': TEXT, 'taxonomy_version': TEXT}, ['taxonomy_id', 'taxonomy_version']),
    'DataAttribute': cls('Data attribute', 'An exact source-system or workbook attribute; bindings require separate governance.',
        {'entity_name': TEXT, 'attribute_name': TEXT, 'registry_reference': TEXT}, ['entity_name', 'attribute_name', 'registry_reference']),
}


def rel(label, definition, domain, range_, minimum=0, maximum=None):
    return {'label': label, 'definition': definition, 'domain': domain.split('|'), 'range': range_.split('|'),
            'min_per_subject': minimum, 'max_per_subject': maximum}


RELATIONSHIPS = {
    'HAS_APPLICABILITY': rel('has applicability', 'Source-backed scope inherited by rules of this policy version.', 'PolicyVersion', 'ConditionGroup', 0, 1),
    'HAS_EXCLUSION': rel('has exclusion', 'Source-backed exclusion from a policy version.', 'PolicyVersion', 'ConditionGroup', 0, 1),
    'APPLIES_FOR': rel('applies for', 'A borrower submits a credit application.', 'Borrower', 'LoanApplication'),
    'REQUESTS_PRODUCT': rel('requests product', 'The product requested by an application.', 'LoanApplication', 'Product', 1, 1),
    'RESULTS_IN': rel('results in', 'An application results in an originated loan; absence does not imply rejection.', 'LoanApplication', 'Loan', 0, 1),
    'BORROWS': rel('borrows', 'A borrower is a party to an originated loan.', 'Borrower', 'Loan'),
    'OF_PRODUCT': rel('of product', 'The product type of an originated loan.', 'Loan', 'Product', 1, 1),
    'GOVERNED_BY': rel('governed by', 'The exact policy version governing a loan; not inferred merely from product mentions.', 'Loan', 'PolicyVersion'),
    'VERSION_OF': rel('version of', 'A policy version belongs to one stable policy identity.', 'PolicyVersion', 'CreditPolicy', 1, 1),
    'CONTAINS_SECTION': rel('contains section', 'A version contains a section.', 'PolicyVersion', 'PolicySection'),
    'PART_OF_VERSION': rel('part of version', 'A section or rule belongs to exactly one policy version.', 'PolicySection|PolicyRule', 'PolicyVersion', 1, 1),
    'PARENT_SECTION': rel('parent section', 'Optional containing section within the same version.', 'PolicySection', 'PolicySection', 0, 1),
    'CONTAINS_RULE': rel('contains rule', 'A policy version or section contains a rule.', 'PolicyVersion|PolicySection', 'PolicyRule'),
    'APPLIES_TO_PRODUCT': rel('applies to product', 'Explicit applicability to a product, distinct from classification.', 'PolicyRule', 'Product'),
    'APPLIES_TO_SEGMENT': rel('applies to segment', 'Explicit applicability to a customer segment.', 'PolicyRule', 'CustomerSegment'),
    'APPLIES_IN': rel('applies in', 'Explicit geographic scope of a rule.', 'PolicyRule', 'Geography'),
    'MEMBER_OF_SEGMENT': rel('member of segment', 'Source-backed customer membership in a segment.', 'Customer', 'CustomerSegment'),
    'USES_METRIC': rel('uses metric', 'A rule uses a defined risk measure.', 'PolicyRule', 'RiskMetric'),
    'HAS_THRESHOLD': rel('has threshold', 'A rule has a numerical boundary.', 'PolicyRule', 'Threshold'),
    'MEASURED_BY': rel('measured by', 'The metric against which a threshold is interpreted.', 'Threshold', 'RiskMetric', 1, 1),
    'HAS_CONDITION': rel('has condition', 'The explicit logical condition for a rule, exception or approval requirement.', 'PolicyRule|Exception|ApprovalRequirement', 'ConditionGroup', 0, 1),
    'HAS_MEMBER': rel('has member', 'A logical expression contains comparison terms or nested expressions.', 'ConditionGroup', 'Condition|ConditionGroup', 1),
    'HAS_EXCEPTION': rel('has exception', 'A rule permits an explicitly stated exception.', 'PolicyRule', 'Exception'),
    'EXCEPTION_TO': rel('exception to', 'The one base rule from which an exception permits deviation.', 'Exception', 'PolicyRule', 1, 1),
    'IMPLEMENTED_BY_RULE': rel('implemented by rule', 'An optional alternative rule specifies the permitted deviation.', 'Exception', 'PolicyRule', 0, 1),
    'REQUIRES_APPROVAL': rel('requires approval', 'A rule or exception requires a decision, not evidence that it has been granted.', 'PolicyRule|Exception', 'ApprovalRequirement'),
    'REQUIRES_APPROVAL_FROM': rel('requires approval from', 'The role or committee required for an approval decision.', 'ApprovalRequirement', 'ApprovalAuthority', 1, 1),
    'REQUIRES_EVIDENCE': rel('requires evidence', 'A rule or approval requires an evidence type.', 'PolicyRule|ApprovalRequirement', 'EvidenceRequirement'),
    'SATISFIES_REQUIREMENT': rel('satisfies requirement', 'A recorded claim that an evidence artifact satisfies a requirement; verification remains explicit.', 'ControlEvidence', 'EvidenceRequirement'),
    'EVIDENCE_FOR': rel('evidence for', 'An evidence artifact supports an application, rule or exception.', 'ControlEvidence', 'LoanApplication|PolicyRule|Exception'),
    'HAS_EFFECTIVE_PERIOD': rel('has effective period', 'An explicitly stated validity period; no period implies no known validity.', 'PolicyVersion|PolicyRule|Exception', 'EffectivePeriod', 0, 1),
    'DERIVED_FROM': rel('derived from', 'A rule is grounded in one or more exact source passages from its own policy version.', 'PolicyRule', 'SourcePassage', 1),
    'SOURCE_IN_VERSION': rel('source in version', 'The policy version containing an exact source passage.', 'SourcePassage', 'PolicyVersion', 1, 1),
    'CLASSIFIED_AS': rel('classified as', 'A semantic entity is classified using an external controlled taxonomy.', 'PolicyRule|Product|CustomerSegment|RiskMetric|Geography', 'TaxonomyConcept'),
    'BINDS_TO_ATTRIBUTE': rel('binds to attribute', 'An explicit proposed or reviewed metric-to-data binding; never inferred from similar labels.', 'RiskMetric', 'DataAttribute'),
}

RULES = [
    ('UNIQUE_IDS', 'Node and relationship IDs must be unique across the instance.'),
    ('TYPED_ENDPOINTS', 'Every relationship endpoint exists and satisfies the declared domain/range, including subclass inheritance.'),
    ('SOURCE_REFERENCES', 'Every assertion and every non-passage entity has exact SourcePassage references.'),
    ('SOURCE_VERSION', 'A rule and its derived source passages belong to the same policy version; source checksum/version agree.'),
    ('CONTAINMENT', 'Section/rule containment and parent-section links agree with PART_OF_VERSION.'),
    ('THRESHOLD_METRIC', 'Each threshold has one metric; its unit is permitted by that metric and the owning rule USES_METRIC.'),
    ('QUANTITATIVE_RULE', 'A QUANTITATIVE rule has at least one threshold and metric.'),
    ('EXCEPTION_LINKS', 'HAS_EXCEPTION and EXCEPTION_TO agree; an implemented alternative has rule_kind EXCEPTION_RULE and shares the base version.'),
    ('CONDITIONS', 'IN/NOT_IN use nonempty lists; EXISTS omits value; other comparisons require scalar values; ordered comparisons require numbers.'),
    ('CONDITION_LOGIC', 'NOT has exactly one member; AND/OR have at least one; condition groups and section parents are acyclic.'),
    ('EFFECTIVE_DATES', 'An end date, when provided, cannot precede the start date.'),
    ('EXAMPLE_ISOLATION', 'EXAMPLE instances are synthetic and use illustrative passages; SOURCE_BACKED instances cannot cite illustrative passages.'),
    ('SYNTHETIC_PROVENANCE', 'An entity supported by synthetic source passages must itself retain the synthetic flag.'),
]


def class_lineage(kind):
    result = []
    while kind:
        result.append(kind)
        kind = CLASSES[kind]['parent']
    return result


def class_properties(kind):
    properties, required = {}, []
    for name in reversed(class_lineage(kind)):
        properties.update(deepcopy(CLASSES[name]['properties']))
        required.extend(CLASSES[name]['required_properties'])
    return properties, required


def semantic_contract():
    return {'ontology_id': NAMESPACE.rstrip(':'), 'version': VERSION, 'namespace': NAMESPACE,
        'status': 'CURRENT', 'purpose': 'Shared business semantic schema for policy extraction, connected knowledge and request assessment.',
        'classes': deepcopy(CLASSES), 'relationships': deepcopy(RELATIONSHIPS),
        'semantic_constraints': [{'code': code, 'definition': text} for code, text in RULES],
        'taxonomic_integration': 'CLASSIFIED_AS references taxonomy IDs and version; it never establishes applicability.',
        'operational_integration': 'Source-backed policy versions, rules, scope and evidence populate the graph used by policy views and compliance matching.',
        'approval_semantics': 'Schema conformance checks structure and consistency; it does not verify source interpretation or grant business approval.',
        'standards': {'json_schema': 'https://json-schema.org/draft/2020-12/schema',
            'owl': 'http://www.w3.org/2002/07/owl#', 'shacl': 'http://www.w3.org/ns/shacl#'}}


def instance_schema():
    definitions = {}
    for kind in CLASSES:
        props, required = class_properties(kind)
        payload = {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}
        if kind == 'Condition':
            payload['allOf'] = [
                {'if': {'properties': {'operator': {'const': 'EXISTS'}}}, 'then': {'not': {'required': ['value']}}, 'else': {'required': ['value']}},
                {'if': {'properties': {'operator': {'enum': ['IN', 'NOT_IN']}}}, 'then': {'properties': {'value': {'type': 'array'}}}, 'else': {'properties': {'value': {'not': {'type': 'array'}}}}},
                {'if': {'properties': {'operator': {'enum': ['GT', 'GTE', 'LT', 'LTE']}}}, 'then': {'properties': {'value': {'type': 'number'}}}},
            ]
        definitions[kind] = {'type': 'object', 'additionalProperties': False,
            'required': ['id', 'type', 'label', 'status', 'synthetic', 'source_refs', 'properties'],
            'properties': {'id': ID, 'type': {'const': kind}, 'label': TEXT, 'status': {'enum': STATUSES},
                'synthetic': {'type': 'boolean'}, 'source_refs': {'type': 'array', 'items': ID,
                    'uniqueItems': True, 'minItems': 0 if kind == 'SourcePassage' else 1}, 'properties': payload}}
    definitions['Relationship'] = {'type': 'object', 'additionalProperties': False,
        'required': ['id', 'subject', 'predicate', 'object', 'status', 'source_refs'],
        'properties': {'id': ID, 'subject': ID, 'predicate': {'enum': list(RELATIONSHIPS)}, 'object': ID,
            'status': {'enum': STATUSES}, 'source_refs': {'type': 'array', 'items': ID, 'minItems': 1, 'uniqueItems': True}}}
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': SCHEMA_ID,
        'title': 'CPI credit policy semantic instance',
        '$comment': 'JSON Schema validates local shapes. The supplied semantic validator also checks endpoint types, cardinalities, provenance and cross-node constraints. RDF exports provide the same semantic checks through SHACL plus a documented transport profile.',
        'type': 'object', 'additionalProperties': False,
        'required': ['ontology_version', 'mode', 'nodes', 'relationships'],
        'properties': {'ontology_version': {'const': VERSION}, 'mode': {'enum': ['EXAMPLE', 'SOURCE_BACKED']},
            'nodes': {'type': 'array', 'minItems': 1, 'maxItems': 100000, 'items': {'oneOf': [{'$ref': '#/$defs/' + k} for k in CLASSES]}},
            'relationships': {'type': 'array', 'maxItems': 300000, 'items': {'$ref': '#/$defs/Relationship'}}}, '$defs': definitions}


@lru_cache(maxsize=1)
def validators():
    from jsonschema import Draft202012Validator, FormatChecker
    schema=instance_schema()
    # Every class has a distinct type const. Dispatching by that const is
    # equivalent to the exported oneOf, without trying 24 shapes per node.
    envelope=deepcopy(schema)
    envelope['properties']['nodes']['items']={'type':'object','required':['type'],
        'properties':{'type':{'enum':list(CLASSES)}}}
    checker=FormatChecker()
    return Draft202012Validator(envelope,format_checker=checker),{
        kind:Draft202012Validator(schema['$defs'][kind],format_checker=checker) for kind in CLASSES}


def index_graph(data, fail):
    """Index graph nodes and check IDs and relationship endpoints."""
    nodes = {}
    ids = set()
    for node in data['nodes']:
        if node['id'] in ids:
            fail('UNIQUE_IDS', 'Duplicate node ID: ' + node['id'])
        ids.add(node['id'])
        nodes[node['id']] = node
        for key, value in node['properties'].items():
            if isinstance(value, float) and not math.isfinite(value):
                fail('JSON_SCHEMA', 'Non-finite number: ' + node['id'] + '/' + key)
    outgoing = {}
    for edge in data['relationships']:
        if edge['id'] in ids:
            fail('UNIQUE_IDS', 'Duplicate assertion ID: ' + edge['id'])
        ids.add(edge['id'])
        a, b = nodes.get(edge['subject']), nodes.get(edge['object'])
        spec = RELATIONSHIPS[edge['predicate']]
        if a is None or b is None:
            fail('TYPED_ENDPOINTS', 'Unknown endpoint: ' + edge['id'])
            continue
        if not set(class_lineage(a['type'])) & set(spec['domain']) or not set(class_lineage(b['type'])) & set(spec['range']):
            fail('TYPED_ENDPOINTS', 'Relationship violates domain/range: ' + edge['id'])
        outgoing.setdefault((edge['subject'], edge['predicate']), []).append(edge['object'])
    return nodes, outgoing


def validate_graph_semantics(data, nodes, targets, one, fail):
    """Check provenance, relationship cardinality, and policy node rules."""
    for item in [*data['nodes'], *data['relationships']]:
        for ref in item['source_refs']:
            if ref not in nodes or nodes[ref]['type'] != 'SourcePassage':
                fail('SOURCE_REFERENCES', 'Evidence must identify a SourcePassage: ' + item['id'])
        if 'synthetic' in item and not item['synthetic'] and any(nodes.get(ref, {}).get('synthetic') for ref in item['source_refs']):
            fail('SYNTHETIC_PROVENANCE', 'Synthetic source provenance must be retained: ' + item['id'])
    for node in nodes.values():
        for predicate, spec in RELATIONSHIPS.items():
            if not set(class_lineage(node['type'])) & set(spec['domain']):
                continue
            values = targets(node, predicate)
            count = len(set(values))
            if count < spec['min_per_subject'] or (spec['max_per_subject'] is not None and count > spec['max_per_subject']):
                fail('CARDINALITY', f"{node['id']} needs {spec['min_per_subject']}..{spec['max_per_subject']} {predicate} links")
            if len(values) != count:
                fail('DUPLICATE_RELATIONSHIP', f"Duplicate {predicate} assertion from {node['id']}")
        kind, props = node['type'], node['properties']
        if data['mode'] == 'EXAMPLE' and not node['synthetic']:
            fail('EXAMPLE_ISOLATION', 'Every illustrative entity must be synthetic: ' + node['id'])
        if kind == 'SourcePassage':
            expected = 'ILLUSTRATIVE_EXAMPLE' if data['mode'] == 'EXAMPLE' else 'POLICY_SOURCE'
            if props['origin'] != expected:
                fail('EXAMPLE_ISOLATION', 'Passage origin conflicts with instance mode: ' + node['id'])
            version = one(node, 'SOURCE_IN_VERSION')
            if version and (version['properties']['version'] != props['version'] or version['properties']['source_checksum'] != props['source_checksum']):
                fail('SOURCE_VERSION', 'Passage version/checksum differs from its PolicyVersion: ' + node['id'])
        if kind == 'PolicyRule':
            version = one(node, 'PART_OF_VERSION')
            for sid in targets(node, 'DERIVED_FROM'):
                passage = nodes[sid]
                if passage['type'] == 'SourcePassage' and (not version or one(passage, 'SOURCE_IN_VERSION') != version):
                    fail('SOURCE_VERSION', 'Rule derives from a different policy version: ' + node['id'])
            if props['rule_kind'] == 'QUANTITATIVE' and (not targets(node, 'HAS_THRESHOLD') or not targets(node, 'USES_METRIC')):
                fail('QUANTITATIVE_RULE', 'Quantitative rule needs a threshold and metric: ' + node['id'])
            for tid in targets(node, 'HAS_THRESHOLD'):
                metric = one(nodes[tid], 'MEASURED_BY')
                if metric and metric['id'] not in targets(node, 'USES_METRIC'):
                    fail('THRESHOLD_METRIC', 'Threshold metric is not used by its owning rule: ' + node['id'])
            for eid in targets(node, 'HAS_EXCEPTION'):
                if targets(nodes[eid], 'EXCEPTION_TO') != [node['id']]:
                    fail('EXCEPTION_LINKS', 'Exception does not point back to its base rule: ' + eid)
        if kind == 'Threshold':
            metric = one(node, 'MEASURED_BY')
            if metric and metric['type'] == 'RiskMetric' and props['unit'] not in metric['properties']['allowed_units']:
                fail('THRESHOLD_METRIC', 'Threshold unit is not allowed by its metric: ' + node['id'])
        if kind == 'Exception':
            base = one(node, 'EXCEPTION_TO')
            alternative = one(node, 'IMPLEMENTED_BY_RULE')
            if base and node['id'] not in targets(base, 'HAS_EXCEPTION'):
                fail('EXCEPTION_LINKS', 'Base rule does not declare this exception: ' + node['id'])
            if alternative and (alternative['properties'].get('rule_kind') != 'EXCEPTION_RULE' or not base or one(alternative, 'PART_OF_VERSION') != one(base, 'PART_OF_VERSION')):
                fail('EXCEPTION_LINKS', 'Alternative rule must be an EXCEPTION_RULE in the same version: ' + node['id'])
        if kind in ('PolicyVersion', 'PolicySection'):
            version = node if kind == 'PolicyVersion' else one(node, 'PART_OF_VERSION')
            for predicate in ('CONTAINS_SECTION', 'CONTAINS_RULE'):
                for child in targets(node, predicate):
                    if one(nodes[child], 'PART_OF_VERSION') != version:
                        fail('CONTAINMENT', 'Contained entity belongs to a different version: ' + child)
        if kind == 'PolicySection':
            parent = one(node, 'PARENT_SECTION')
            if parent and one(parent, 'PART_OF_VERSION') != one(node, 'PART_OF_VERSION'):
                fail('CONTAINMENT', 'Parent section belongs to a different version: ' + node['id'])
        if kind == 'EffectivePeriod' and props.get('end_date') and date.fromisoformat(props['end_date']) < date.fromisoformat(props['start_date']):
            fail('EFFECTIVE_DATES', 'End date precedes start date: ' + node['id'])
        if kind == 'ConditionGroup' and props['logic'] == 'NOT' and len(targets(node, 'HAS_MEMBER')) != 1:
            fail('CONDITION_LOGIC', 'NOT must have exactly one member: ' + node['id'])


def validate_instance(data):
    """Validate transport shape and graph-wide semantic consistency without writes."""
    validator,typed_validators=validators()
    errors = [{'code': 'JSON_SCHEMA', 'path': '/'.join(map(str, e.absolute_path)), 'message': e.message[:500]}
        for e in sorted(validator.iter_errors(data), key=lambda e: str(list(e.absolute_path)))][:100]
    if not errors:
        for index,node in enumerate(data['nodes']):
            errors.extend({'code':'JSON_SCHEMA','path':f'nodes/{index}/'+'/'.join(map(str,e.absolute_path)),
                'message':e.message[:500]} for e in typed_validators[node['type']].iter_errors(node))
            if len(errors)>=100:
                errors=errors[:100];break
    if errors:
        return {'conforms': False, 'ontology_version': VERSION, 'errors': errors}

    def fail(code, message, path=''):
        if len(errors) < 100:
            errors.append({'code': code, 'path': path, 'message': message})

    nodes, outgoing = index_graph(data, fail)

    # Do not traverse structurally invalid endpoints in later consistency checks.
    if errors:
        return {'conforms': False, 'ontology_version': VERSION, 'errors': errors}

    def targets(node, predicate):
        return outgoing.get((node['id'], predicate), [])

    def one(node, predicate):
        values = targets(node, predicate)
        return nodes.get(values[0]) if len(values) == 1 else None

    validate_graph_semantics(data, nodes, targets, one, fail)
    import networkx as nx
    for predicate in ('HAS_MEMBER', 'PARENT_SECTION'):
        graph = nx.DiGraph((e['subject'], e['object']) for e in data['relationships'] if e['predicate'] == predicate)
        if not nx.is_directed_acyclic_graph(graph):
            fail('CONDITION_LOGIC', predicate + ' cannot contain a cycle')
    return {'conforms': not errors, 'ontology_version': VERSION, 'errors': errors,
        'counts': {'nodes': len(data['nodes']), 'relationships': len(data['relationships'])}}


def example_instance():
    """One explicitly fictional scenario exercising every business class."""
    source_text = ('ILLUSTRATIVE EXAMPLE ONLY. Example Borrower applies for an SME home loan. '
        'Example Policy version 1.0 contains section Eligibility and rule R-LTV: for SME home loans in India, '
        'LTV must be at most 80 percent. An exception permits at most 85 percent when a compensating collateral '
        'condition is satisfied and a credit manager approves. A valuation report is required. '
        'The example policy is effective from 2026-01-01 to 2026-12-31. '
        'DTI and credit score are metric definitions only; no thresholds for them are asserted.')
    checksum = hashlib.sha256(source_text.encode()).hexdigest()
    prefix = 'urn:cpi:example:'
    source = prefix + 'passage'
    nodes, edges = [], []

    def node(key, kind, label, **properties):
        nodes.append({'id': prefix + key, 'type': kind, 'label': label, 'status': 'PROPOSED',
            'synthetic': True, 'source_refs': [] if kind == 'SourcePassage' else [source], 'properties': properties})

    def edge(a, p, b):
        edges.append({'id': prefix + 'assertion-' + str(len(edges) + 1), 'subject': prefix + a,
            'predicate': p, 'object': prefix + b, 'status': 'PROPOSED', 'source_refs': [source]})

    node('borrower', 'Borrower', 'Example Borrower', customer_reference='EXAMPLE-CUSTOMER', customer_kind='ORGANIZATION')
    node('application', 'LoanApplication', 'Example application', application_reference='EXAMPLE-APP')
    node('loan', 'Loan', 'Example originated loan', loan_reference='EXAMPLE-LOAN', currency='INR')
    node('policy', 'CreditPolicy', 'Example Credit Policy', policy_reference='EXAMPLE-POLICY', risk_domain='Credit risk')
    node('version', 'PolicyVersion', 'Example policy v1.0', version='1.0', source_checksum=checksum)
    node('section', 'PolicySection', 'Eligibility', section_reference='EXAMPLE-SECTION-1')
    node('rule', 'PolicyRule', 'LTV at most 80 percent', rule_reference='R-LTV', rule_kind='QUANTITATIVE')
    node('alternative', 'PolicyRule', 'Exception ceiling at most 85 percent', rule_reference='R-LTV-EX', rule_kind='EXCEPTION_RULE')
    node('condition', 'Condition', 'Compensating collateral is present', field='additional_collateral_verified', operator='EQ', value=True)
    node('condition-group', 'ConditionGroup', 'Exception conditions', logic='AND')
    node('threshold', 'Threshold', 'At most 80 percent', operator='LTE', value=80, unit='%')
    node('exception-threshold', 'Threshold', 'At most 85 percent', operator='LTE', value=85, unit='%')
    node('segment', 'CustomerSegment', 'SME', segment_code='SME')
    node('product', 'Product', 'Home loan', product_code='HOME_LOAN')
    node('geography', 'Geography', 'India', geography_code='IN', code_scheme='ISO-3166-1-alpha-2')
    node('ltv', 'RiskMetric', 'Loan to value', metric_key='ltv', allowed_units=['%'], formula='loan_amount / collateral_value * 100')
    node('dti', 'RiskMetric', 'Debt to income', metric_key='dti', allowed_units=['%'], formula='debt_obligations / income * 100')
    node('credit-score', 'RiskMetric', 'Credit score', metric_key='credit_score', allowed_units=['score_points'])
    node('exception', 'Exception', 'Compensating collateral exception', exception_reference='EX-LTV')
    node('approval', 'ApprovalRequirement', 'Credit manager decision required', decision_type='APPROVAL')
    node('authority', 'ApprovalAuthority', 'Credit manager', authority_code='CREDIT_MANAGER', authority_kind='ROLE')
    node('evidence-required', 'EvidenceRequirement', 'Valuation report requirement', evidence_type='COLLATERAL_VALUATION_REPORT')
    node('evidence', 'ControlEvidence', 'Example valuation report', evidence_reference='EXAMPLE-REPORT', evidence_type='COLLATERAL_VALUATION_REPORT', verification_state='UNVERIFIED')
    node('period', 'EffectivePeriod', 'Example 2026 validity', start_date='2026-01-01', end_date='2026-12-31')
    node('passage', 'SourcePassage', 'Illustrative source passage', document_reference='EXAMPLE-POLICY', version='1.0', source_checksum=checksum, text=source_text, origin='ILLUSTRATIVE_EXAMPLE')
    node('taxonomy', 'TaxonomyConcept', 'LTV taxonomy reference', taxonomy_id='PTX-TOPIC-ltv', taxonomy_version='policy-classification-v1')
    node('attribute', 'DataAttribute', 'Illustrative data attribute', entity_name='EXAMPLE_LOAN', attribute_name='ltv_percentage', registry_reference='EXAMPLE-REGISTRY')
    for a, p, b in [
        ('borrower', 'APPLIES_FOR', 'application'), ('borrower', 'BORROWS', 'loan'), ('borrower', 'MEMBER_OF_SEGMENT', 'segment'),
        ('application', 'REQUESTS_PRODUCT', 'product'), ('application', 'RESULTS_IN', 'loan'), ('loan', 'OF_PRODUCT', 'product'), ('loan', 'GOVERNED_BY', 'version'),
        ('version', 'VERSION_OF', 'policy'), ('version', 'CONTAINS_SECTION', 'section'), ('section', 'PART_OF_VERSION', 'version'),
        ('section', 'CONTAINS_RULE', 'rule'), ('section', 'CONTAINS_RULE', 'alternative'),
        ('rule', 'PART_OF_VERSION', 'version'), ('alternative', 'PART_OF_VERSION', 'version'),
        ('rule', 'APPLIES_TO_PRODUCT', 'product'), ('rule', 'APPLIES_TO_SEGMENT', 'segment'), ('rule', 'APPLIES_IN', 'geography'),
        ('rule', 'USES_METRIC', 'ltv'), ('alternative', 'USES_METRIC', 'ltv'),
        ('rule', 'HAS_THRESHOLD', 'threshold'), ('alternative', 'HAS_THRESHOLD', 'exception-threshold'),
        ('threshold', 'MEASURED_BY', 'ltv'), ('exception-threshold', 'MEASURED_BY', 'ltv'),
        ('rule', 'HAS_EXCEPTION', 'exception'), ('exception', 'EXCEPTION_TO', 'rule'), ('exception', 'IMPLEMENTED_BY_RULE', 'alternative'),
        ('exception', 'HAS_CONDITION', 'condition-group'), ('condition-group', 'HAS_MEMBER', 'condition'),
        ('exception', 'REQUIRES_APPROVAL', 'approval'), ('approval', 'REQUIRES_APPROVAL_FROM', 'authority'),
        ('rule', 'REQUIRES_EVIDENCE', 'evidence-required'), ('evidence', 'EVIDENCE_FOR', 'application'),
        ('version', 'HAS_EFFECTIVE_PERIOD', 'period'), ('rule', 'DERIVED_FROM', 'passage'), ('alternative', 'DERIVED_FROM', 'passage'),
        ('passage', 'SOURCE_IN_VERSION', 'version'), ('rule', 'CLASSIFIED_AS', 'taxonomy'), ('ltv', 'BINDS_TO_ATTRIBUTE', 'attribute'),
    ]:
        edge(a, p, b)
    return {'ontology_version': VERSION, 'mode': 'EXAMPLE', 'nodes': nodes, 'relationships': edges}
