"""Explicit, reviewed synthetic fixtures. These never amend the supplied workbook."""
from .ingestion import LABEL
from .models import Concept, Provenance

POLICY_TEXT = f'''# Demonstration Credit Standard

{LABEL}

Version: DEMO-1.0

Effective date: 2026-10-01

## 1. Approval requirements

1.1 For unsecured business loans above INR 5 million, borrowers having an internal credit rating below BBB require approval from the Senior Credit Committee.

1.2 For unsecured business loans above INR 4 million, approval from the Regional Credit Committee is required.

## 2. Documentation and exceptions

2.1 For SME borrowers requesting more than INR 2 million, audited financial statements are required, except where a sovereign guarantee is present.

2.2 For unsecured business loans, collateral type must be None.

## 3. Monitoring

3.1 For borrowers in Manufacturing or Construction, annual credit review is required.

3.2 For unsecured business loans above INR 8 million, approval from the Board Credit Committee is required.

3.3 For unsecured business loans above INR 10 million, approval from the Executive Credit Committee is required.

3.4 For borrowers with an internal credit rating below B, new lending is prohibited.
'''

REFERENCE_TEXT = f'''# Demonstration risk reference

{LABEL}

Version: DEMO-1.0

The following explicit triples are manufactured examples for reviewer training.

Borrower -> HAS_RISK_RATING -> Internal Rating

Credit Facility -> HAS_PRODUCT -> Product

Credit Facility -> HAS_EXPOSURE -> Requested Amount

Credit Facility -> SECURED_BY -> Collateral

Borrower -> BELONGS_TO -> Customer Segment

Policy Rule -> APPLIES_TO -> Credit Facility

Policy Rule -> HAS_CONDITION -> Condition

Borrower -> OPERATES_IN -> Country
'''

SAMPLE_REQUEST = {'borrower': 'ABC Manufacturing Ltd', 'currency': 'INR', 'as_of': '2026-11-01',
                  'attributes': {'product': 'Unsecured Business Loan', 'amount': 6000000,
                                 'rating': 'BB', 'segment': 'SME', 'industry': 'Manufacturing',
                                 'collateral': 'None', 'country': 'India', 'sovereign_guarantee': False}}

# Each supported mock template is the exact complete clause, not a loose regex.
TEMPLATES = [
    dict(text='1.1 For unsecured business loans above INR 5 million, borrowers having an internal credit rating below BBB require approval from the Senior Credit Committee.',
         name='Elevated exposure · lower rating', scope=[('product', '=', 'Unsecured Business Loan')],
         conditions=[('amount', '>', 5000000), ('rating', '<', 'BBB')], action='Approval Required', authority='Senior Credit Committee'),
    dict(text='1.2 For unsecured business loans above INR 4 million, approval from the Regional Credit Committee is required.',
         name='Regional approval threshold', scope=[('product', '=', 'Unsecured Business Loan')],
         conditions=[('amount', '>', 4000000)], action='Approval Required', authority='Regional Credit Committee'),
    dict(text='2.1 For SME borrowers requesting more than INR 2 million, audited financial statements are required, except where a sovereign guarantee is present.',
         name='SME financial statements', scope=[('segment', '=', 'SME')], conditions=[('amount', '>', 2000000)],
         action='Documentation Required', value='Audited financial statements', exception=[('sovereign_guarantee', '=', True)]),
    dict(text='2.2 For unsecured business loans, collateral type must be None.',
         name='Unsecured product collateral check', scope=[('product', '=', 'Unsecured Business Loan')],
         conditions=[('collateral', '=', 'None')], action='Product Eligibility', value='Unsecured classification confirmed'),
    dict(text='3.1 For borrowers in Manufacturing or Construction, annual credit review is required.',
         name='Industrial sector annual review', scope=[], conditions=[('industry', '=', 'Manufacturing'), ('industry', '=', 'Construction')],
         logic='OR', action='Monitoring Required', value='Annual credit review'),
    dict(text='3.2 For unsecured business loans above INR 8 million, approval from the Board Credit Committee is required.',
         name='Board approval threshold', scope=[('product', '=', 'Unsecured Business Loan')], conditions=[('amount', '>', 8000000)],
         action='Approval Required', authority='Board Credit Committee'),
    dict(text='3.3 For unsecured business loans above INR 10 million, approval from the Executive Credit Committee is required.',
         name='Historical executive threshold', scope=[('product', '=', 'Unsecured Business Loan')], conditions=[('amount', '>', 10000000)],
         action='Approval Required', authority='Executive Credit Committee'),
    dict(text='3.4 For borrowers with an internal credit rating below B, new lending is prohibited.',
         name='Low rating prohibition', scope=[], conditions=[('rating', '<', 'B')], action='Lending Prohibited')]


def demo_concepts():
    source = Provenance(document_id='DEMO-MODEL', document_name='Synthetic demonstration vocabulary',
                        origin='SYNTHETIC_DEMO', passage=LABEL + '; isolated test vocabulary; not part of the workbook.',
                        provider='MockLLMProvider')
    specs = [
        ('risk', 'Credit Risk', 'DOMAIN', 'UNKNOWN', []),
        ('borrower', 'Borrower', 'ENTITY', 'string', []),
        ('facility', 'Credit Facility', 'ENTITY', 'string', []),
        ('policy-rule', 'Policy Rule', 'ENTITY', 'string', []),
        ('condition', 'Condition', 'ENTITY', 'string', []),
        ('product', 'Product', 'ATTRIBUTE', 'string', ['Unsecured Business Loan', 'Secured Business Loan']),
        ('amount', 'Requested Amount', 'ATTRIBUTE', 'decimal', []),
        ('rating', 'Internal Rating', 'ATTRIBUTE', 'ordered_enum', ['D', 'C', 'CC', 'CCC', 'B', 'BB', 'BBB', 'A', 'AA', 'AAA']),
        ('segment', 'Customer Segment', 'ATTRIBUTE', 'string', ['SME', 'Corporate', 'Retail']),
        ('industry', 'Industry', 'ATTRIBUTE', 'string', ['Manufacturing', 'Construction', 'Services']),
        ('collateral', 'Collateral', 'ATTRIBUTE', 'string', ['None', 'Property', 'Cash']),
        ('country', 'Country', 'ATTRIBUTE', 'string', ['India', 'Singapore', 'United Kingdom']),
        ('sovereign_guarantee', 'Sovereign Guarantee', 'ATTRIBUTE', 'boolean', ['true', 'false'])]
    concepts = []
    for key, name, kind, dtype, values in specs:
        concepts.append(Concept(concept_id='DEMO-' + key, preferred_name=name, description=LABEL,
                                parent_concept=None if key == 'risk' else 'DEMO-risk',
                                kind=kind, data_type=dtype, allowed_values=values,
                                source=source, status='APPROVED', risk_domain='Credit Risk',
                                review_notes='Approved synthetic fixture for the demonstration; reviewer: DEMO_FIXTURE.',
                                metadata={'request_attribute': key if kind == 'ATTRIBUTE' else None,
                                          'rating_order': 'worst_to_best' if key == 'rating' else None}))
    concepts.append(Concept(concept_id='DEMO-sme-alias', preferred_name='SME',
                            synonyms=['small business borrower', 'small business'], kind='VALUE',
                            parent_concept='DEMO-segment', source=source, status='APPROVED',
                            risk_domain='Credit Risk', metadata={'request_attribute': 'segment'},
                            review_notes='DEMO_FIXTURE reviewed synthetic synonym.'))
    return concepts
