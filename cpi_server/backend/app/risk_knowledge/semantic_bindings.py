"""Explicit links between the semantic graph, policy taxonomy, and deal fields."""
from .policy_taxonomy import FACETS
from .semantic_extraction import digest
from ..services.credit_data import ALIASES, GROUPS, DERIVATIONS


# The runtime matcher resolves these deal fields using the same exact aliases.
MATCH_FIELDS = {
    'product': 'facility.facility_type',
    'customer_segment': 'borrower.customer_segment',
    'borrower_type': 'borrower.borrower_type',
    'counterparty_type': 'counterparty.counterparty_type',
    'tenor': 'facility.tenor_months',
    'interest_coverage_ratio': 'metric.interest_coverage',
    'total_debt_to_ebitda': 'metric.debt_to_ebitda',
}

SCOPE_TERMS = {
    'industry': ('Industry', 'APPLIES_TO_INDUSTRY'),
    'industry_sector': ('Sector', None),
    'subsector': ('Subsector', 'APPLIES_TO_SUBSECTOR'),
    'industry_tier': ('IndustryTier', 'APPLIES_TO_INDUSTRY_TIER'),
    'borrower_type': ('BorrowerType', 'APPLIES_TO_BORROWER_TYPE'),
    'product': ('Product', 'APPLIES_TO_PRODUCT'),
    'facility': ('Product', 'APPLIES_TO_PRODUCT'),
    'customer_segment': ('CustomerSegment', 'APPLIES_TO_SEGMENT'),
    'geography': ('Geography', 'APPLIES_IN'),
    'jurisdiction': ('Jurisdiction', 'APPLIES_IN'),
    'booking_jurisdiction': ('Jurisdiction', 'APPLIES_IN'),
    'country_of_incorporation': ('Country', 'APPLIES_IN'),
    'country_of_domicile': ('Country', 'APPLIES_IN'),
    'country_of_risk': ('Country', 'APPLIES_IN'),
}


def terms_for_comparison(comparison):
    scope = SCOPE_TERMS.get(comparison['field'])
    if scope is None or comparison['operator'] == 'EXISTS':
        return ()
    kind, predicate = scope
    value = comparison.get('value')
    values = value if isinstance(value, list) else [value]
    return [(kind, predicate, name) for name in values if isinstance(name, str) and name.strip()]


def term_definition(kind, value):
    """Use controlled aliases where available, then identify the literal label."""
    label = ' '.join(value.split())
    facet = {'Product': 'product', 'CustomerSegment': 'customer_segment', 'Geography': 'geography'}.get(kind)
    for name, aliases in FACETS.get(facet, ()):
        if label.casefold() in {name.casefold(), *(alias.casefold() for alias in aliases)}:
            label = name
            break
    code = label.casefold()
    if kind == 'Product':
        return label, {'product_code': code}
    if kind == 'CustomerSegment':
        return label, {'segment_code': code}
    if kind in ('Geography', 'Country', 'Jurisdiction', 'Region'):
        return label, {'geography_code': code, 'code_scheme': 'REPORTED_LABEL'}
    return label, {}


def term_identifier(kind, label, properties):
    return 'urn:cpi:' + kind.lower() + ':' + digest([label.casefold(), properties])[:20]


def attribute_definition(field):
    key = MATCH_FIELDS.get(field) or ALIASES.get(field)
    if key is None and (field in GROUPS or field in DERIVATIONS or field in MATCH_FIELDS.values()):
        key = field
    if key:
        entity, attribute = key.split('.', 1)
        return key, {'entity_name': entity, 'attribute_name': attribute, 'registry_reference': 'cpi:credit-data:' + key}
