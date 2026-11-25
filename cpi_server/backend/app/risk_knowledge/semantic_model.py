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
from .competency_projection import ORDERED_RATING_FIELDS, RATINGS

VERSION = '1.4.0'
COMPATIBLE_VERSIONS = (VERSION, '1.3.0', '1.2.0')
NAMESPACE = 'urn:cpi:ontology:credit-policy:'
SCHEMA_ID = 'urn:cpi:schema:credit-policy:' + VERSION
STATUSES = ['PROPOSED', 'APPROVED', 'REJECTED', 'SUPERSEDED']
EVIDENCE_CLASSES = ('SourcePassage', 'OperationalEvidence')
# Source dictionary anchors are modeling evidence. They do not supply request values.
WORKBOOK_ANCHORS = [
    ('EX1751', 'CRWA_Report_View', 'Client Industry Code', 'OPERATES_IN_INDUSTRY'),
    ('EX1750', 'CRWA_Report_View', 'Client Country of Operations', 'OPERATES_IN_GEOGRAPHY'),
    ('NEW0025', 'Dim_Party', 'Client Domicile Country', 'DOMICILED_IN'),
    ('DEL0045', 'Fact_Retail_Payments_Delinquency_Loss', 'Current Probability of Default (PD)', 'RiskMetric'),
]


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
         'source_rule_code': TEXT,
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
        {'authority_code': TEXT, 'authority_kind': prop(enum=['ROLE', 'COMMITTEE', 'UNSPECIFIED'])}, ['authority_code', 'authority_kind']),
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

# Domain vocabulary is shared across deals, policy scope, and assessments.
CLASSES.update({
    'Party': cls('Party', 'A person, organization, or group with a role in a credit relationship.'),
    'LegalEntity': cls('Legal entity', 'An independently constituted organization that can be a parent entity.', parent='Party'),
    'Counterparty': cls('Counterparty', 'A party on the other side of a credit transaction.', parent='Party'),
    'Guarantor': cls('Guarantor', 'A party that provides a guarantee.', parent='Party'),
    'Sponsor': cls('Sponsor', 'A party that supports a borrower or a financed transaction.', parent='Party'),
    'Lender': cls('Lender', 'A party providing credit.', parent='Party'),
    'Tenant': cls('Tenant', 'A party leasing financed or pledged property.', parent='Party'),
    'CorporateGroup': cls('Corporate group', 'A group of affiliated parties.', parent='Party'),
    'CreditRequest': cls('Credit request', 'A request for one or more credit facilities.',
        {'request_reference': TEXT, 'requested_amount': prop('number', minimum=0), 'workflow_stage': TEXT}),
    'Facility': cls('Facility', 'A requested or committed credit arrangement.'),
    'Country': cls('Country', 'A country identified under an explicit geographic code scheme.', parent='Geography'),
    'Jurisdiction': cls('Jurisdiction', 'A territory under a particular legal or regulatory authority.', parent='Geography'),
    'Region': cls('Region', 'A geographic grouping of territories.', parent='Geography'),
    'BookingLocation': cls('Booking location', 'The office or location where a facility is booked.'),
    'Industry': cls('Industry', 'An economic classification of a party or financed activity.'),
    'Sector': cls('Sector', 'A broad economic classification.'),
    'Subsector': cls('Subsector', 'A finer economic classification within a sector.'),
    'BusinessActivity': cls('Business activity', 'An economic activity conducted by a party or financed by a facility.'),
    'BorrowerType': cls('Borrower type', 'A classification used for borrower eligibility.'),
    'Exposure': cls('Exposure', 'A credit exposure measured at the applicable entity and reporting scope.',
        {'amount': prop('number', minimum=0), 'as_of': DATE}),
    'Limit': cls('Limit', 'An authorized exposure ceiling.'),
    'Collateral': cls('Collateral', 'An asset or security pledged against credit.'),
    'Guarantee': cls('Guarantee', 'A commitment by a guarantor to support an obligation.'),
    'Tenor': cls('Tenor', 'The duration of a facility in months.', {'months': prop('number', minimum=0)}, ['months']),
    'Currency': cls('Currency', 'The currency in which a credit amount is denominated.', {'currency_code': TEXT}, ['currency_code']),
    'Purpose': cls('Purpose', 'The stated intended use of funding.'),
    'RiskAttribute': cls('Risk attribute', 'A qualitative or quantitative characteristic used in credit-risk analysis.'),
    'CreditRating': cls('Credit rating', 'An observed credit rating under an identified rating type.',
        {'rating_code': TEXT, 'rating_type': prop(enum=['INTERNAL', 'EXTERNAL'])}, ['rating_code', 'rating_type'], parent='RiskAttribute'),
    'RiskGrade': cls('Risk grade', 'A grade assigned under a risk classification scale.', parent='RiskAttribute'),
    'RiskObservation': cls('Risk observation', 'An observed deal risk value with the unit supplied by its source.',
        {'risk_key': TEXT, 'observed_value': prop('number'), 'unit': TEXT}, ['risk_key', 'observed_value']),
    'PolicyClass': cls('Policy class', 'A policy category or topic in the current policy taxonomy.', parent='TaxonomyConcept'),
    'PolicyConcern': cls('Policy concern', 'A source-backed subject or dependency used to navigate rules.',
        {'concern_code': TEXT}, ['concern_code']),
    'IndustryTier': cls('Industry tier', 'A risk tier assigned to an industry under the relevant classification.'),
    'OperationalEvidence': cls('Operational evidence', 'A source reference for a deal fact or an assessment output.',
        {'source_type': TEXT, 'source_reference': TEXT, 'field_name': TEXT}, ['source_type', 'source_reference']),
    'RuleAssessment': cls('Rule assessment', 'An evaluation of a specific credit request against a specific policy rule.',
        {'evaluated_on': DATE}, ['evaluated_on']),
    'DecisionOutcome': cls('Decision outcome', 'The recorded result of a rule assessment.',
        {'outcome_code': prop(enum=['PASS', 'BREACH', 'EXCEPTION', 'REFERRAL', 'WARNING', 'UNABLE_TO_ASSESS', 'NOT_APPLICABLE'])},
        ['outcome_code']),
})
for child, parent in [('Customer', 'Party'), ('LoanApplication', 'CreditRequest'),
                      ('Loan', 'Facility'), ('RiskMetric', 'RiskAttribute')]:
    CLASSES[child]['parent'] = parent


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
    'APPLIES_TO_PRODUCT': rel('applies to product', 'Explicit applicability to a product.', 'PolicyVersion|PolicyRule', 'Product'),
    'APPLIES_TO_SEGMENT': rel('applies to segment', 'Explicit applicability to a customer segment.', 'PolicyVersion|PolicyRule', 'CustomerSegment'),
    'APPLIES_IN': rel('applies in', 'Explicit geographic scope, including jurisdiction when identified as such.', 'PolicyVersion|PolicyRule', 'Geography'),
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

DOMAIN_RELATIONSHIPS = {
    'OPERATES_IN_INDUSTRY': rel('operates in industry', 'The industry in which the party operates.', 'Party', 'Industry'),
    'OPERATES_IN_GEOGRAPHY': rel('operates in geography', 'A geography explicitly identified as a location of operations.', 'Party', 'Geography'),
    'HAS_REPORTED_GEOGRAPHY': rel('has reported geography', 'Geography reported without a specific legal, booking, or risk role.', 'Party', 'Geography'),
    'INCORPORATED_IN': rel('incorporated in', 'The country of legal incorporation.', 'Party', 'Country'),
    'DOMICILED_IN': rel('domiciled in', 'The country of domicile as reported by the source.', 'Party', 'Country'),
    'HAS_COUNTRY_OF_RISK': rel('has country of risk', 'The country attributed to the party, facility, or exposure for credit-risk analysis.', 'Party|Facility|Exposure', 'Country'),
    'IN_REGION': rel('in region', 'The geography belongs to a geographic region.', 'Geography', 'Region'),
    'BELONGS_TO_GROUP': rel('belongs to group', 'The party is a member of a corporate group.', 'Party', 'CorporateGroup'),
    'HAS_PARENT_LEGAL_ENTITY': rel('has parent legal entity', 'The identified parent organization of a party.', 'Party', 'LegalEntity'),
    'IN_SECTOR': rel('in sector', 'The party or economic classification belongs to a sector.', 'Party|Industry|Subsector', 'Sector'),
    'IN_SUBSECTOR': rel('in subsector', 'The party or activity is classified in a subsector.', 'Party|BusinessActivity', 'Subsector'),
    'HAS_BUSINESS_ACTIVITY': rel('has business activity', 'The activity attributed to a party or financed by a facility.', 'Party|Facility', 'BusinessActivity'),
    'HAS_BORROWER_TYPE': rel('has borrower type', 'The explicitly reported borrower classification.', 'Borrower', 'BorrowerType'),
    'HAS_CREDIT_RATING': rel('has credit rating', 'A rating attributed to the party.', 'Party', 'CreditRating'),
    'HAS_RISK_GRADE': rel('has risk grade', 'A grade attributed to the party or facility.', 'Party|Facility', 'RiskGrade'),
    'HAS_RISK_ATTRIBUTE': rel('has risk attribute', 'A risk measure or characteristic, such as PD, LGD, LTV, concentration, country risk or industry risk.', 'Party|Facility|Exposure|CreditRequest', 'RiskAttribute'),
    'HAS_RISK_OBSERVATION': rel('has risk observation', 'A measured risk value recorded in the request context.', 'Party|Facility|Exposure|CreditRequest', 'RiskObservation'),
    'HAS_EXPOSURE': rel('has exposure', 'An exposure attributed to the party or facility.', 'Party|Facility', 'Exposure'),
    'SUBJECT_TO_LIMIT': rel('subject to limit', 'A documented ceiling covering the exposure or facility.', 'Exposure|Facility', 'Limit'),
    'REQUESTED_BY': rel('requested by', 'The borrower seeking credit.', 'CreditRequest', 'Borrower'),
    'REQUESTS_FACILITY': rel('requests facility', 'A facility the borrower asks the lender to provide.', 'CreditRequest', 'Facility'),
    'HAS_PRODUCT': rel('has product', 'The product used to structure a requested or originated facility.', 'Facility', 'Product'),
    'HAS_COUNTERPARTY': rel('has counterparty', 'A counterparty to the facility.', 'Facility', 'Counterparty'),
    'HAS_SPONSOR': rel('has sponsor', 'A sponsor for the request or the facility.', 'CreditRequest|Facility', 'Sponsor'),
    'HAS_LENDER': rel('has lender', 'A lender providing the facility.', 'Facility', 'Lender'),
    'HAS_TENOR': rel('has tenor', 'The requested or contractual facility duration.', 'Facility', 'Tenor', 0, 1),
    'HAS_RECOMMENDED_TENOR': rel('has recommended tenor', 'A recommended facility duration recorded by the credit system.', 'Facility', 'Tenor', 0, 1),
    'HAS_TENANT': rel('has tenant', 'A tenant of property financed or pledged to the facility.', 'Facility|Collateral', 'Tenant'),
    'HAS_COLLATERAL': rel('has collateral', 'Collateral pledged for the facility.', 'Facility', 'Collateral'),
    'HAS_GUARANTEE': rel('has guarantee', 'A guarantee supporting the facility.', 'Facility', 'Guarantee'),
    'PROVIDED_BY_GUARANTOR': rel('provided by guarantor', 'The party providing the guarantee.', 'Guarantee', 'Guarantor'),
    'BOOKED_IN_JURISDICTION': rel('booked in jurisdiction', 'The jurisdiction in which the facility is booked.', 'Facility', 'Jurisdiction'),
    'BOOKED_AT': rel('booked at', 'The booking office or location for the facility.', 'Facility', 'BookingLocation'),
    'LOCATED_IN_JURISDICTION': rel('located in jurisdiction', 'The jurisdiction of the booking location.', 'BookingLocation', 'Jurisdiction'),
    'DENOMINATED_IN': rel('denominated in', 'The recorded currency of the credit amount.', 'CreditRequest|Facility|Exposure|Limit', 'Currency'),
    'HAS_PURPOSE': rel('has purpose', 'The stated purpose of the request or facility.', 'CreditRequest|Facility', 'Purpose'),
}
APPLICABILITY_RELATIONSHIPS = {
    'APPLIES_TO_INDUSTRY': rel('applies to industry', 'An industry explicitly required by policy or rule scope. Full scope follows the condition logic.', 'PolicyVersion|PolicyRule', 'Industry'),
    'APPLIES_TO_BORROWER_TYPE': rel('applies to borrower type', 'An explicit borrower type in policy or rule scope.', 'PolicyVersion|PolicyRule', 'BorrowerType'),
    'APPLIES_TO_SUBSECTOR': rel('applies to subsector', 'An expressly included economic or property subsector. Full scope follows the policy and rule conditions.', 'PolicyVersion|PolicyRule', 'Subsector'),
    'APPLIES_TO_INDUSTRY_TIER': rel('applies to industry tier', 'An explicitly included industry risk tier.', 'PolicyVersion|PolicyRule', 'IndustryTier'),
    'DOCUMENTS_PRODUCT_SCOPE': rel('documents product scope', 'A rule statement identifies this product. Other eligibility conditions remain in the source.', 'PolicyRule', 'Product'),
    'COMPARES_SCOPE_VALUE': rel('compares scope value', 'A typed value tested by a condition. The operator and its parent group determine how the comparison is used.', 'Condition', 'Industry|Sector|Subsector|IndustryTier|BorrowerType|Product|CustomerSegment|Geography'),
    'EVALUATES_RISK_ATTRIBUTE': rel('evaluates risk attribute', 'The rule checks a quantitative measure or qualitative risk characteristic.', 'PolicyRule', 'RiskAttribute'),
    'TESTS_ATTRIBUTE': rel('tests attribute', 'A condition names a field with an explicit binding in the deal fact registry.', 'Condition', 'DataAttribute'),
    'OBSERVES_DATA_ATTRIBUTE': rel('observes data attribute', 'The observation is sourced from a registered deal attribute.', 'RiskObservation', 'DataAttribute', 0, 1),
}
DECISION_RELATIONSHIPS = {
    'HAS_RULE_ASSESSMENT': rel('has rule assessment', 'The credit request has a recorded rule evaluation.', 'CreditRequest', 'RuleAssessment'),
    'ASSESSES_RULE': rel('assesses rule', 'The exact rule checked in this evaluation.', 'RuleAssessment', 'PolicyRule', 1, 1),
    'HAS_OUTCOME': rel('has outcome', 'The result produced by this request-specific rule evaluation.', 'RuleAssessment', 'DecisionOutcome', 1, 1),
}
RELATIONSHIPS.update({
    **DOMAIN_RELATIONSHIPS,
    'HAS_VERSION': rel('has version', 'The stable policy identity has an explicitly identified version.', 'CreditPolicy', 'PolicyVersion'),
    'DERIVED_FROM_POLICY_CLASS': rel('derived from policy class', 'An explicit derivation from a policy class. Classification alone does not establish derivation.', 'PolicyRule', 'PolicyClass'),
    'CONCERNS': rel('concerns', 'A source-backed rule subject or dependency.', 'PolicyRule', 'PolicyConcern'),
    'REQUIRES_APPROVAL_ON_BREACH': rel('requires approval on breach', 'The cited approval or escalation is explicitly triggered by a threshold breach.', 'PolicyRule', 'ApprovalRequirement'),
    'REQUIRES_APPROVAL_ABOVE_THRESHOLD': rel('requires approval above threshold', 'The cited approval or escalation applies above an authority or transaction threshold.', 'PolicyRule', 'ApprovalRequirement'),
    **APPLICABILITY_RELATIONSHIPS,
    **DECISION_RELATIONSHIPS,
})

RULES = [
    ('UNIQUE_IDS', 'Node and relationship IDs must be unique across the instance.'),
    ('TYPED_ENDPOINTS', 'Every relationship endpoint exists and satisfies the declared domain/range, including subclass inheritance.'),
    ('SOURCE_REFERENCES', 'Every assertion and non-evidence entity references policy passages or operational evidence. Rules retain their exact source passages.'),
    ('SOURCE_VERSION', 'A rule and its derived source passages belong to the same policy version; source checksum/version agree.'),
    ('CONTAINMENT', 'Section/rule containment and parent-section links agree with PART_OF_VERSION.'),
    ('THRESHOLD_METRIC', 'Each threshold has one metric; its unit is permitted by that metric and the owning rule USES_METRIC.'),
    ('QUANTITATIVE_RULE', 'A QUANTITATIVE rule has at least one threshold and metric.'),
    ('EXCEPTION_LINKS', 'HAS_EXCEPTION and EXCEPTION_TO agree; an implemented alternative has rule_kind EXCEPTION_RULE and shares the base version.'),
    ('CONDITIONS', 'Membership uses a nonempty list. EXISTS omits its value. Ordered comparisons use numbers or recognized credit rating codes.'),
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


def ontology_layers():
    domain_classes = set(CLASSES) - {
        'CreditPolicy', 'PolicyVersion', 'PolicySection', 'PolicyRule', 'Condition', 'ConditionGroup',
        'Threshold', 'Exception', 'ApprovalRequirement', 'ApprovalAuthority', 'EvidenceRequirement',
        'ControlEvidence', 'EffectivePeriod', 'SourcePassage', 'TaxonomyConcept', 'PolicyClass', 'PolicyConcern',
        'DataAttribute', 'OperationalEvidence', 'RuleAssessment', 'DecisionOutcome',
    }
    applicability = {*APPLICABILITY_RELATIONSHIPS, 'HAS_APPLICABILITY', 'HAS_EXCLUSION', 'APPLIES_TO_PRODUCT',
                     'APPLIES_TO_SEGMENT', 'APPLIES_IN', 'USES_METRIC', 'BINDS_TO_ATTRIBUTE', 'GOVERNED_BY'}
    domain = {*DOMAIN_RELATIONSHIPS, 'APPLIES_FOR', 'REQUESTS_PRODUCT', 'RESULTS_IN', 'BORROWS', 'OF_PRODUCT', 'MEMBER_OF_SEGMENT'}
    decision = {'OperationalEvidence', 'RuleAssessment', 'DecisionOutcome'}
    layers = [
        ('Domain', 'Deals, parties, geography, economic classifications, facilities and risk.', domain_classes, domain),
        ('Policy', 'Versioned source evidence, taxonomy, rules, thresholds, exceptions and approvals.',
         set(CLASSES) - domain_classes - decision - {'DataAttribute'}, set(RELATIONSHIPS) - domain - applicability - set(DECISION_RELATIONSHIPS)),
        ('Applicability', 'Policy scope and rule conditions connected to domain values and deal attributes.', {'DataAttribute'}, applicability),
        ('Decision', 'Request-specific rule evaluations and recorded outcomes.', decision, DECISION_RELATIONSHIPS),
    ]
    return [{'name': name, 'description': description, 'classes': sorted(classes), 'relationships': sorted(relationships)}
            for name, description, classes, relationships in layers]


def semantic_contract():
    return {'ontology_id': NAMESPACE.rstrip(':'), 'version': VERSION, 'namespace': NAMESPACE,
        'status': 'CURRENT', 'purpose': 'Shared business semantic schema for policy extraction, connected knowledge and request assessment.',
        'classes': deepcopy(CLASSES), 'relationships': deepcopy(RELATIONSHIPS),
        'layers': ontology_layers(),
        'model_sources': {
            'taxonomy': 'policy-classification-v1',
            'credit_data_registry': 'app/services/credit_data.py',
            'deal_schema': 'cd_cpi_server/backend/app/schemas/deal.py',
            'policy_corpus': 'Current policy versions, extracted rules, and reviewed policy scope records.',
            'risk_data_dictionary': 'Risk Data Model_Oct 2026.xlsx / Table_Attribute_Details',
            'risk_data_dictionary_anchors': [
                {'row_id': row, 'entity': entity, 'attribute': field, 'model_term': term}
                for row, entity, field, term in WORKBOOK_ANCHORS
            ],
        },
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
                {'if': {'properties': {'operator': {'enum': ['GT', 'GTE', 'LT', 'LTE']}}},
                 'then': {'anyOf': [
                     {'properties': {'value': {'type': 'number'}}},
                     {'properties': {'field': {'enum': list(ORDERED_RATING_FIELDS)}, 'value': {'enum': list(RATINGS)}},
                      'not': {'required': ['unit']}},
                 ]}},
            ]
        definitions[kind] = {'type': 'object', 'additionalProperties': False,
            'required': ['id', 'type', 'label', 'status', 'synthetic', 'source_refs', 'properties'],
            'properties': {'id': ID, 'type': {'const': kind}, 'label': TEXT, 'status': {'enum': STATUSES},
                'synthetic': {'type': 'boolean'}, 'source_refs': {'type': 'array', 'items': ID,
                    'uniqueItems': True, 'minItems': 0 if kind in EVIDENCE_CLASSES else 1}, 'properties': payload}}
    definitions['Relationship'] = {'type': 'object', 'additionalProperties': False,
        'required': ['id', 'subject', 'predicate', 'object', 'status', 'source_refs'],
        'properties': {'id': ID, 'subject': ID, 'predicate': {'enum': list(RELATIONSHIPS)}, 'object': ID,
            'status': {'enum': STATUSES}, 'source_refs': {'type': 'array', 'items': ID, 'minItems': 1, 'uniqueItems': True}}}
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': SCHEMA_ID,
        'title': 'CPI credit policy semantic instance',
        '$comment': 'JSON Schema validates local shapes. The supplied semantic validator also checks endpoint types, cardinalities, provenance and cross-node constraints. RDF exports provide the same semantic checks through SHACL plus a documented transport profile.',
        'type': 'object', 'additionalProperties': False,
        'required': ['ontology_version', 'mode', 'nodes', 'relationships'],
        'properties': {'ontology_version': {'enum': list(COMPATIBLE_VERSIONS)}, 'mode': {'enum': ['EXAMPLE', 'SOURCE_BACKED']},
            'nodes': {'type': 'array', 'minItems': 1, 'maxItems': 100000, 'items': {'oneOf': [{'$ref': '#/$defs/' + k} for k in CLASSES]}},
            'relationships': {'type': 'array', 'maxItems': 300000, 'items': {'$ref': '#/$defs/Relationship'}}}, '$defs': definitions}


@lru_cache(maxsize=1)
def validators():
    from jsonschema import Draft202012Validator, FormatChecker
    schema=instance_schema()
    # Every class has a distinct type const. Dispatching by that const is
    # equivalent to the exported oneOf, without trying every shape per node.
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
            if ref not in nodes or nodes[ref]['type'] not in EVIDENCE_CLASSES:
                fail('SOURCE_REFERENCES', 'Evidence must identify a SourcePassage or OperationalEvidence: ' + item['id'])
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
    """An explicitly fictional scenario spanning all four layers."""
    source_text = ('ILLUSTRATIVE EXAMPLE ONLY. Example Borrower applies for an SME home loan. '
        'Example Policy version 1.0 contains section Eligibility and rule R-LTV: for SME home loans in India, '
        'LTV must be at most 80 percent. An exception permits at most 85 percent when a compensating collateral '
        'condition is satisfied and a credit manager approves. A valuation report is required. '
        'The example policy is effective from 2026-01-01 to 2026-12-31. '
        'DTI and credit score are metric definitions only; no thresholds for them are asserted. '
        'The policy and LTV rule apply to property services. The borrower operates in property services and '
        'is incorporated in India. It requests a 60-month facility. '
        'An illustrative assessment at 75 percent LTV records a pass for the base rule.')
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
    node('taxonomy', 'PolicyClass', 'Loan-to-value taxonomy reference', taxonomy_id='PTX-TOPIC-ltv', taxonomy_version='policy-classification-v1')
    node('attribute', 'DataAttribute', 'Illustrative data attribute', entity_name='EXAMPLE_LOAN', attribute_name='ltv_percentage', registry_reference='EXAMPLE-REGISTRY')
    node('industry', 'Industry', 'Property services')
    node('country', 'Country', 'India', geography_code='IN', code_scheme='ISO-3166-1-alpha-2')
    node('facility', 'Facility', 'Example requested facility')
    node('tenor', 'Tenor', '60 months', months=60)
    node('assessment', 'RuleAssessment', 'Illustrative LTV assessment', evaluated_on='2026-01-02')
    node('pass', 'DecisionOutcome', 'Pass', outcome_code='PASS')
    node('scope', 'ConditionGroup', 'Industry scope', logic='AND')
    node('industry-condition', 'Condition', 'Industry is property services', field='industry', operator='EQ', value='Property services')
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
        ('borrower', 'OPERATES_IN_INDUSTRY', 'industry'), ('borrower', 'INCORPORATED_IN', 'country'),
        ('application', 'REQUESTED_BY', 'borrower'), ('application', 'REQUESTS_FACILITY', 'facility'),
        ('facility', 'HAS_PRODUCT', 'product'), ('facility', 'HAS_TENOR', 'tenor'),
        ('policy', 'HAS_VERSION', 'version'), ('version', 'APPLIES_TO_PRODUCT', 'product'),
        ('version', 'APPLIES_TO_INDUSTRY', 'industry'), ('rule', 'APPLIES_TO_INDUSTRY', 'industry'),
        ('version', 'HAS_APPLICABILITY', 'scope'), ('rule', 'HAS_CONDITION', 'scope'),
        ('scope', 'HAS_MEMBER', 'industry-condition'), ('industry-condition', 'COMPARES_SCOPE_VALUE', 'industry'),
        ('rule', 'EVALUATES_RISK_ATTRIBUTE', 'ltv'), ('application', 'HAS_RULE_ASSESSMENT', 'assessment'),
        ('assessment', 'ASSESSES_RULE', 'rule'), ('assessment', 'HAS_OUTCOME', 'pass'),
    ]:
        edge(a, p, b)
    return {'ontology_version': VERSION, 'mode': 'EXAMPLE', 'nodes': nodes, 'relationships': edges}
