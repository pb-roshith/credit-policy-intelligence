"""Versioned executable policy vocabulary; never learned from LLM relationships.

These are explicit application bindings to credit_data.GROUPS, not assertions
that similarly named spreadsheet fields are interchangeable. Spreadsheet links
are added only for exact source-schema labels and remain visible as provenance.
"""
ONTOLOGY_VERSION = 'credit-policy-ontology-v2'
METRICS = {
    'dscr': {'label': 'Debt Service Coverage Ratio', 'terms': ['debt service coverage ratio', 'dscr'],
             'field': 'dscr', 'units': ['x'], 'formula': ['net operating income', 'total debt service'],
             'taxonomy_entities':['Fact_Customer_Financial_Statements']},
    'tenor': {'label': 'Tenor', 'terms': ['tenor', 'loan tenor'],
              'field': 'recommended_tenor_years', 'units': ['years'],
              'taxonomy_entities':['Fact_Loan_Account_Exposure']},
    'leverage': {'label': 'Debt to EBITDA', 'terms': ['debt to ebitda', 'total debt to ebitda', 'leverage ratio'],
                 'field': 'leverage_ratio', 'units': ['x']},
    'ltv': {'label': 'Loan to Value Ratio', 'terms': ['loan to value ratio', 'loan-to-value ratio', 'ltv', 'ltv ratio'],
            'field': 'ltv', 'units': ['%']},
    'interest_coverage': {'label': 'Interest Coverage Ratio', 'terms': ['interest coverage ratio', 'interest coverage', 'icr'],
                          'field': 'icr', 'units': ['x']},
    'exposure': {'label': 'Exposure', 'terms': ['exposure', 'total exposure'],
                 'field': 'exposure', 'units': ['USD', 'INR', 'EUR', 'GBP']},
    'requested_amount': {'label': 'Requested Amount', 'terms': ['requested amount', 'loan amount'],
                         'field': 'requested_amount', 'units': ['USD', 'INR', 'EUR', 'GBP']},
}
FACILITIES = {
    'term loans': 'Term Loan', 'term loan': 'Term Loan',
    'revolving credit facilities': 'Revolver', 'revolving credit facility': 'Revolver',
    'revolvers': 'Revolver', 'revolver': 'Revolver',
    'project finance facilities': 'Project Finance', 'project finance': 'Project Finance',
    'working capital facilities': 'Working Capital',
    'mortgage loans':'Mortgage', 'auto loans':'Auto Loan', 'secured personal loans':'Secured Personal Loan',
}
SCOPE_VOCABULARIES = {
    'property_type': {
        'Investment Property':['investment properties','investment property'],
        'Primary Residence':['primary residences','primary residence'],
        'Secondary Residence':['secondary homes','secondary or vacation homes'],
        'Vacation Home':['vacation homes','secondary or vacation homes'],
    },
    'loan_program': {
        'Conventional':['conventional loans','conventional'],
        'Government-Insured':['government-insured loans','government-insured','loans insured by a government agency'],
        'Jumbo':['jumbo loans'],
    },
    'vehicle_condition': {'New':['new vehicles'],'Used':['used vehicles']},
}
DOCUMENTS = {'audited financial statements': 'audited_financial_statements',
             'collateral valuation report': 'collateral_valuation_report',
             'credit approval memorandum': 'credit_approval_memorandum'}
SCOPE_FIELDS = {'facility', 'borrower_credit_rating', 'rating', 'currency', 'industry',
                'geography', 'customer_segment', 'borrower_type', 'status',*SCOPE_VOCABULARIES}
RATINGS = ('D','C','CC','CCC-','CCC','CCC+','B-','B','B+','BB-','BB','BB+',
           'BBB-','BBB','BBB+','A-','A','A+','AA-','AA','AA+','AAA')
PREDICATES = {
    'CONTAINS': ('PolicyDocument', 'SourceSpan'),
    'DERIVED_FROM': ('PolicyRequirement', 'SourceSpan'),
    'USES_METRIC': ('PolicyRequirement', 'PolicyMetric'),
    'CONSTRAINS': ('PolicyRequirement', 'PolicyConstraint'),
    'HAS_SCOPE': ('PolicyRequirement', 'PolicyCondition'),
    'HAS_EXCEPTION': ('PolicyRequirement', 'PolicyCondition'),
    'REQUIRES_DOCUMENT': ('PolicyRequirement', 'PolicyDocumentType'),
    'MAPS_TO': ('PolicyMetric', 'ATTRIBUTE'),
}


def ontology_contract():
    return {'version': ONTOLOGY_VERSION, 'metrics': METRICS, 'facilities': FACILITIES,
            'documents': DOCUMENTS, 'scope_fields': sorted(SCOPE_FIELDS),
            'scope_vocabularies':SCOPE_VOCABULARIES,
            'rating_order_worst_to_best': list(RATINGS), 'predicates': PREDICATES}
