"""Project request facts and rule outcomes onto the business ontology."""
from math import isfinite

from ..risk_knowledge.semantic_bindings import attribute_definition, term_definition, term_identifier
from ..risk_knowledge.semantic_extraction import digest
from ..risk_knowledge.semantic_model import VERSION
from .credit_data import provenance_sources
from .semantic_matching import Facts

OUTCOMES = {
    'Pass': 'PASS', 'Breach': 'BREACH', 'Exception': 'EXCEPTION', 'Referral': 'REFERRAL',
    'Manual Review Required': 'REFERRAL', 'Warning': 'WARNING',
    'Unable to Assess': 'UNABLE_TO_ASSESS', 'Not Applicable': 'NOT_APPLICABLE',
}
RISK_FIELDS = {
    'ltv': 'Loan to value', 'dscr': 'Debt service coverage', 'leverage_ratio': 'Debt to EBITDA',
    'icr': 'Interest coverage', 'probability_of_default': 'Probability of default',
    'loss_given_default': 'Loss given default', 'concentration_limit_utilization': 'Concentration utilization',
    'country_risk': 'Country risk', 'industry_risk': 'Industry risk',
}


def request_overlay(request_id, proposal, *, evaluated_on=None, evaluation_reference=None, findings=(), rule_nodes=None):
    """Build the authorized request's graph extension, referencing policy rule IDs."""
    root = 'urn:cpi:request:' + digest(request_id)[:24]
    nodes, edges = {}, {}
    facts = Facts(proposal)

    def node(identifier, kind, label, refs=(), synthetic=False, **properties):
        if identifier in nodes:
            existing = nodes[identifier]
            existing['source_refs'] = sorted(set(existing['source_refs']) | set(refs))
            existing['synthetic'] |= synthetic
        else:
            nodes[identifier] = {'id': identifier, 'type': kind, 'label': label, 'status': 'PROPOSED',
                                 'synthetic': synthetic, 'properties': properties, 'source_refs': list(refs)}
        return identifier

    def evidence(field, source_type, reference, synthetic=False):
        identifier = root + ':evidence:' + digest([field, source_type, reference])[:20]
        return node(identifier, 'OperationalEvidence', field, synthetic=synthetic,
                    source_type=source_type, source_reference=reference, field_name=field)

    def read(field):
        value, unit, source = facts.get(field)
        if isinstance(value, str):
            value = value.strip()
        if value is None or value == '':
            return None, unit, None
        provenance = source.get('provenance') or {}
        kind = provenance.get('source_type') or source.get('source_type') or 'STORED_REQUEST'
        reference = provenance.get('source_identifier') or provenance.get('source_document_id') or source.get('binding') or request_id
        ref = evidence(field, kind, str(reference), kind == 'SYNTHETIC' or
                       bool(provenance.get('source_type') and 'SYNTHETIC' in provenance_sources(provenance)))
        return value, unit, ref

    def edge(subject, predicate, target, refs):
        identifier = 'urn:cpi:assertion:' + digest([subject, predicate, target])[:24]
        edges[identifier] = {'id': identifier, 'subject': subject, 'object': target, 'predicate': predicate,
                             'source_refs': list(refs), 'status': 'PROPOSED'}

    def linked(subject, predicate, kind, field):
        value, _, ref = read(field)
        if not isinstance(value, str) or not ref:
            return
        label, props = term_definition(kind, value)
        # Only controlled or literal classification values are shared with the policy graph.
        identifier = term_identifier(kind, label, props) if kind in {
            'Industry', 'Sector', 'Product', 'CustomerSegment', 'BorrowerType', 'Geography', 'Country', 'Jurisdiction',
        } else root + ':' + field
        if kind == 'Currency':
            props['currency_code'] = label.upper()
        target = node(identifier, kind, label, [ref], nodes[ref]['synthetic'], **props)
        edge(subject, predicate, target, [ref])

    def measurement(subject, predicate, kind, field, property_name, label):
        value, _, ref = read(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            return
        target = node(root + ':' + field, kind, label, [ref], nodes[ref]['synthetic'],
                      **{property_name: value})
        edge(subject, predicate, target, [ref])

    request_ref = evidence('credit_request_number', 'STORED_REQUEST', request_id)
    amount, _, amount_ref = read('requested_amount')
    stage, _, stage_ref = read('status')
    props = {'request_reference': request_id}
    refs = [request_ref]
    if isinstance(amount, (int, float)) and not isinstance(amount, bool) and isfinite(amount) and amount >= 0:
        props['requested_amount'] = amount
        refs.append(amount_ref)
    if isinstance(stage, str) and stage:
        props['workflow_stage'] = stage
        refs.append(stage_ref)
    node(root, 'CreditRequest', request_id, refs, any(nodes[ref]['synthetic'] for ref in refs), **props)
    linked(root, 'DENOMINATED_IN', 'Currency', 'currency')
    for field, label in RISK_FIELDS.items():
        value, unit, ref = read(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            continue
        props = {'risk_key': field, 'observed_value': value}
        if isinstance(unit, str) and unit:
            props['unit'] = unit
        synthetic = nodes[ref]['synthetic']
        observation = node(root + ':risk:' + field, 'RiskObservation', label, [ref], synthetic, **props)
        edge(root, 'HAS_RISK_OBSERVATION', observation, [ref])
        binding = attribute_definition(field)
        if binding:
            key, attributes = binding
            target = node(term_identifier('DataAttribute', key, attributes), 'DataAttribute', key, [ref], synthetic, **attributes)
            edge(observation, 'OBSERVES_DATA_ATTRIBUTE', target, [ref])
    borrower_name, _, name_ref = read('borrower_name')
    if isinstance(borrower_name, str) and name_ref:
        borrower = node(root + ':borrower', 'Borrower', borrower_name, [name_ref], nodes[name_ref]['synthetic'])
        edge(root, 'REQUESTED_BY', borrower, [name_ref])
        for predicate, kind, field in [
            ('OPERATES_IN_INDUSTRY', 'Industry', 'industry'), ('IN_SECTOR', 'Sector', 'sector'),
            ('MEMBER_OF_SEGMENT', 'CustomerSegment', 'customer_segment'), ('HAS_BORROWER_TYPE', 'BorrowerType', 'borrower_type'),
            ('HAS_REPORTED_GEOGRAPHY', 'Geography', 'geography'), ('INCORPORATED_IN', 'Country', 'country_of_incorporation'),
            ('DOMICILED_IN', 'Country', 'country_of_domicile'), ('HAS_COUNTRY_OF_RISK', 'Country', 'country_of_risk'),
            ('OPERATES_IN_GEOGRAPHY', 'Country', 'country_of_operations'), ('BELONGS_TO_GROUP', 'CorporateGroup', 'corporate_group'),
            ('HAS_PARENT_LEGAL_ENTITY', 'LegalEntity', 'parent_legal_entity'), ('HAS_RISK_GRADE', 'RiskGrade', 'risk_grade'),
        ]:
            linked(borrower, predicate, kind, field)
        for field, rating_type in [('rating', 'INTERNAL'), ('borrower_credit_rating', 'EXTERNAL')]:
            rating, _, ref = read(field)
            if isinstance(rating, str) and ref:
                target = node(root + ':' + field, 'CreditRating', rating, [ref], nodes[ref]['synthetic'],
                              rating_code=rating, rating_type=rating_type)
                edge(borrower, 'HAS_CREDIT_RATING', target, [ref])
        measurement(borrower, 'HAS_EXPOSURE', 'Exposure', 'exposure', 'amount', 'Current exposure')

    product, _, facility_ref = read('product')
    if isinstance(product, str) and facility_ref:
        facility = node(root + ':facility', 'Facility', 'Requested facility', [facility_ref], nodes[facility_ref]['synthetic'])
        edge(root, 'REQUESTS_FACILITY', facility, [facility_ref])
        for predicate, kind, field in [
            ('HAS_PRODUCT', 'Product', 'product'), ('DENOMINATED_IN', 'Currency', 'currency'),
            ('HAS_PURPOSE', 'Purpose', 'loan_purpose'), ('BOOKED_IN_JURISDICTION', 'Jurisdiction', 'booking_jurisdiction'),
            ('BOOKED_AT', 'BookingLocation', 'booking_location'), ('HAS_COLLATERAL', 'Collateral', 'collateral_type'),
            ('HAS_TENANT', 'Tenant', 'tenant'), ('HAS_LENDER', 'Lender', 'lender'), ('HAS_SPONSOR', 'Sponsor', 'sponsor'),
            ('HAS_COUNTERPARTY', 'Counterparty', 'counterparty'),
        ]:
            linked(facility, predicate, kind, field)
        tenor, _, tenor_ref = read('tenure')
        if isinstance(tenor, (int, float)) and not isinstance(tenor, bool) and isfinite(tenor) and tenor > 0:
            target = node(root + ':tenure', 'Tenor', 'Requested tenor', [tenor_ref], nodes[tenor_ref]['synthetic'], months=tenor)
            edge(facility, 'HAS_TENOR', target, [tenor_ref])
        else:
            tenor, unit, tenor_ref = read('tenor_months')
            if isinstance(tenor, (int, float)) and not isinstance(tenor, bool) and isfinite(tenor) and tenor > 0:
                recommended = nodes[tenor_ref]['properties']['source_reference'] == 'recommended_tenor_years'
                months = tenor * 12 if recommended or unit in ('year', 'years') else tenor
                target = node(root + ':tenor_months', 'Tenor', 'Recommended tenor' if recommended else 'Facility tenor',
                              [tenor_ref], nodes[tenor_ref]['synthetic'], months=months)
                edge(facility, 'HAS_RECOMMENDED_TENOR' if recommended else 'HAS_TENOR', target, [tenor_ref])

    for finding in findings:
        rule = rule_nodes[finding['rule_id']]
        outcome = OUTCOMES[finding['result']]
        synthetic = bool(finding['synthetic_inputs']) or rule['synthetic']
        assessment = root + ':assessment:' + digest([evaluation_reference, rule['id'], finding['rule_version'], outcome])[:24]
        ref = evidence('rule_assessment', 'ASSESSMENT_ENGINE', assessment, synthetic)
        refs = [ref, *rule['source_refs']]
        node(assessment, 'RuleAssessment', finding['rule_name'], refs, synthetic, evaluated_on=evaluated_on)
        outcome_id = node(assessment + ':outcome', 'DecisionOutcome', finding['result'], refs, synthetic, outcome_code=outcome)
        edge(root, 'HAS_RULE_ASSESSMENT', assessment, [ref])
        edge(assessment, 'ASSESSES_RULE', rule['id'], refs)
        edge(assessment, 'HAS_OUTCOME', outcome_id, refs)

    used_refs = {ref for item in [*nodes.values(), *edges.values()] for ref in item['source_refs']}
    return {'ontology_version': VERSION, 'request_node_id': root,
            'nodes': [item for item in nodes.values() if item['type'] != 'OperationalEvidence' or item['id'] in used_refs],
            'relationships': list(edges.values())}
