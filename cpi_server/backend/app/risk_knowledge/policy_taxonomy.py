"""Source-evidenced policy classification, independent of executable knowledge.

Vocabulary is curated; occurrences and hierarchy branches are derived from current
source passages. Occurrence is a classification proposal, never applicability.
"""
import hashlib
import json
import re
from collections import Counter, defaultdict

VERSION = 'policy-classification-v1'

# key, preferred label, definition/inclusion criteria, explicit source aliases.
CATEGORIES = [
    ('eligibility', 'Eligibility', 'Borrower qualification and underwriting criteria.', ['eligibility', 'underwriting criteria', 'underwriting standards', 'eligible borrower']),
    ('limits', 'Limits and thresholds', 'Quantitative ceilings, floors and risk appetite limits.', ['quantitative limits', 'threshold', 'ceiling', 'minimum', 'maximum', 'floor', 'concentration limit']),
    ('collateral', 'Collateral', 'Security eligibility, valuation, coverage and haircuts.', ['collateral', 'security valuation', 'haircut']),
    ('documentation', 'Documentation', 'Required records, documents and evidence retention.', ['documentation', 'document retention', 'loan file', 'evidence requirements', 'required documents']),
    ('exceptions', 'Exceptions', 'Policy deviations, waivers and compensating factors.', ['exception', 'exceptions', 'waiver', 'override', 'compensating factors']),
    ('approval', 'Approval authority', 'Decision rights, delegated authorities, governance and escalation.', ['approval', 'approval authority', 'governance', 'delegated authority', 'escalation']),
    ('monitoring', 'Monitoring', 'Ongoing controls, alerts, periodic review and surveillance.', ['monitoring', 'surveillance', 'early warning', 'watchlist', 'periodic review']),
    ('reporting', 'Reporting', 'Management, regulatory and portfolio reports.', ['reporting', 'reports', 'report generation']),
    ('servicing', 'Servicing and collections', 'Payment administration, arrears, collections and customer contact.', ['delinquency', 'collections', 'past due', 'past-due', 'promise to pay', 'contact strategy', 'payment allocation', 'cure', 'missed installments', 'promises']),
    ('remediation', 'Remediation and recovery', 'Hardship, restructuring, impaired assets, recoveries and disposals.', ['hardship', 'forbearance', 'restructuring', 'modification', 'recovery', 'recoveries', 'write-off', 'write off', 'debt sale', 'non-performing', 'special assets']),
    ('pricing', 'Pricing and returns', 'Risk-based pricing, spread and return requirements.', ['pricing', 'spread grid', 'raroc', 'risk-adjusted return']),
    ('capital', 'Capital and provisioning', 'Capital, risk-weighted assets, impairment and provisioning.', ['capital', 'risk-weighted assets', 'rwa', 'provisioning', 'impairment']),
    ('scope', 'Scope and applicability', 'Explicit scope statements and jurisdictional coverage.', ['scope', 'applicability']),
    ('definitions', 'Definitions', 'Definitions, formulas and terminology.', ['definitions', 'definition', 'glossary']),
    ('data', 'Data quality and evidence', 'Data lineage, reconciliation, evidence quality and calculation controls.', ['reconciliation', 'governed data', 'lineage', 'missing data', 'stale', 'conflicting evidence', 'verified fact', 'calculation', 'evidence checklist']),
    ('conduct', 'Customer treatment and conduct', 'Customer segmentation, vulnerability, communication and legal treatment.', ['conduct', 'vulnerability', 'segmented', 'customer treatment', 'customer circumstances', 'misrepresent', 'legal and product rules']),
    ('ai', 'AI governance', 'Controls on automated interpretation, human accountability and AI use.', ['genai', 'ai boundary', 'human accountability', 'human oversight', 'autonomously', 'grounding']),
    ('purpose', 'Purpose and objectives', 'Policy purpose and intended outcomes, distinct from operational requirements.', ['purpose', 'objectives']),
    ('training', 'Training and evaluation', 'Training instructions, evaluation tests, synthetic scenarios and prompts.', ['training and evaluation', 'training scenarios', 'training prompts']),
]
TOPICS = [
    ('ltv', 'LTV', 'Loan amount relative to collateral value.', ['ltv', 'loan-to-value', 'loan to value']),
    ('income', 'Income', 'Borrower income and verification.', ['income', 'salary', 'salaries']),
    ('bureau', 'Bureau score', 'External consumer credit scores or bureau reports.', ['bureau score', 'credit score', 'fico', 'credit bureau']),
    ('dti', 'DTI', 'Debt obligations relative to borrower income.', ['dti', 'debt-to-income', 'debt to income']),
    ('dscr', 'DSCR', 'Cash flow relative to debt service.', ['dscr', 'debt service coverage', 'debt-service coverage']),
    ('leverage', 'Leverage', 'Debt relative to earnings or capital.', ['leverage', 'debt-to-ebitda', 'debt to ebitda']),
    ('tenor', 'Tenor and duration', 'Loan maturity, tenor and credit duration.', ['tenor', 'maturity', 'duration']),
    ('rating', 'Credit rating', 'Internal or external borrower risk ratings.', ['credit rating', 'risk rating', 'borrower rating', 'ratings']),
    ('valuation', 'Collateral valuation', 'Appraisal, valuation and revaluation of security.', ['appraisal', 'appraised', 'collateral valuation', 'revaluation']),
    ('haircut', 'Collateral haircut', 'Valuation deductions used for secured exposure.', ['haircut', 'haircuts']),
    ('coverage', 'Interest and collateral coverage', 'Interest or collateral coverage ratios.', ['interest coverage', 'icr', 'collateral coverage', 'coverage ratio']),
    ('concentration', 'Exposure and concentration', 'Single-name, sector and portfolio concentration.', ['concentration', 'exposure limit', 'enterprise limits', 'sub-sector limit']),
    ('country', 'Country risk', 'Country, cross-border and sovereign credit risk.', ['country risk', 'sovereign risk', 'cross-border']),
    ('fx', 'Foreign currency risk', 'Currency mismatch and foreign currency lending.', ['foreign currency', 'currency mismatch', 'fx risk']),
    ('liquidity', 'Portfolio liquidity', 'Liquidity and marketability of credit assets.', ['liquidity', 'marketability']),
    ('covenants', 'Covenants', 'Financial and nonfinancial covenant controls.', ['covenant', 'covenants']),
    ('pricing', 'Spread and RAROC', 'Spread and risk-adjusted profitability measures.', ['spread', 'raroc', 'risk-adjusted return']),
    ('capital', 'Capital and RWA', 'Capital floors and risk-weighted asset treatment.', ['capital floor', 'capital adequacy', 'rwa', 'risk-weighted']),
    ('dpd', 'Days past due', 'Arrears aging and overdue payment measures.', ['days past due', 'dpd', 'aging', 'arrears', 'delinquent amount']),
    ('collections', 'Collection treatment', 'Contact, cure, repayment promises and collections.', ['collections', 'promise to pay', 'contact strategy', 'cure', 'roll rate']),
    ('hardship', 'Hardship and forbearance', 'Customer hardship and temporary payment relief.', ['hardship', 'forbearance', 'payment relief']),
    ('restructuring', 'Restructuring and modification', 'Changes to contractual credit terms.', ['restructuring', 'modification', 'modified terms']),
    ('npl', 'Non-performing loans', 'Nonperforming credit identification and treatment.', ['non-performing', 'nonperforming', 'npl', 'unlikely to pay']),
    ('watchlist', 'Watchlist and early warning', 'Special mention and deterioration indicators.', ['watchlist', 'special mention', 'early warning']),
    ('recovery', 'Recovery and special assets', 'Workout, recovery and special asset management.', ['recovery', 'recoveries', 'special assets', 'workout']),
    ('writeoff', 'Write-off', 'Accounting write-off decisions and controls.', ['write-off', 'write off', 'writeoff']),
    ('debtsale', 'Debt sale', 'Disposal and transfer of distressed debt.', ['debt sale', 'debt-sale', 'loan sale']),
    ('authority', 'Decision and escalation authority', 'Delegation and escalation of credit decisions.', ['approval authority', 'approval authorities', 'delegated authority', 'escalation']),
    ('documents', 'Required evidence', 'Credit file documents, statements and supporting evidence.', ['audited financial statements', 'valuation report', 'approval memorandum', 'document retention', 'evidence requirements']),
]
FACETS = {
    'policy_area': [
        ('Retail', ['retail', 'consumer lending']), ('SME', ['sme', 'small and medium']),
        ('Commercial', ['commercial', 'corporate lending', 'corporate credit']),
        ('Commercial real estate', ['commercial real estate', 'cre']),
        ('Enterprise', ['enterprise-wide', 'enterprise limits', 'bank-wide']),
    ],
    'product': [
        ('Home loan', ['home loan', 'home loans', 'mortgage', 'mortgages', 'mortgage loans']),
        ('Home equity line of credit', ['heloc', 'helocs', 'home equity line of credit', 'home equity lines of credit']),
        ('Auto loan', ['auto loan', 'auto loans', 'vehicle loan', 'vehicle loans']),
        ('Secured personal loan', ['secured personal loan', 'secured personal loans']),
        ('Term loan', ['term loan', 'term loans']),
        ('Revolving credit', ['revolver', 'revolvers', 'revolving credit', 'revolving facilities']),
        ('Project finance', ['project finance']), ('Working capital', ['working capital']),
        ('Construction loan', ['construction loan', 'construction loans', 'construction lending']),
        ('Credit card', ['credit card', 'credit cards']),
    ],
    'customer_segment': [
        ('Salaried', ['salaried']), ('Self-employed', ['self-employed', 'self employed']),
        ('SME', ['sme']), ('Corporate', ['corporate borrower', 'corporate borrowers']),
    ],
    'geography': [(v, [v]) for v in ['India', 'United States', 'United Kingdom', 'European Union', 'Singapore']],
}


def identifier(*parts):
    return 'PTX-' + hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:20]


def matches(text, aliases):
    """Literal vocabulary matches with word boundaries; retain exact evidence."""
    hits = []
    for alias in aliases:
        # PDF line wrapping can split multiword expressions.
        pattern = r'(?<!\w)' + r'\s+'.join(re.escape(p) for p in alias.split()) + r'(?!\w)'
        hit = re.search(pattern, text, re.I)
        if hit:
            hits.append({'alias': alias, 'quote': hit.group(), 'start': hit.start(), 'end': hit.end()})
    return hits


def source_rows(connection_factory):
    """Read current sources only, in one read-only consistent transaction.

    No summaries, rule titles, legacy versions or customer data are classified.
    """
    with connection_factory() as connection:
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        documents = connection.execute('''SELECT p.policy_id,p.title,p.file_name,p.source_type,
            p.version AS catalog_version,v.id AS policy_version_id,v.version,v.checksum,
            v.effective_date FROM policy_documents p LEFT JOIN policy_versions v
            ON v.policy_id=p.policy_id AND v.is_current ORDER BY p.policy_id''').fetchall()
        clauses = connection.execute('''SELECT cl.*,v.policy_id FROM policy_clauses cl
            JOIN policy_versions v ON v.id=cl.policy_version_id WHERE v.is_current
            ORDER BY v.policy_id,cl.sequence,cl.id''').fetchall()
    return [dict(d) for d in documents], [dict(c) for c in clauses]


def heading_for(clause):
    text = clause['source_excerpt'].strip()
    first = text.splitlines()[0] if text else ''
    if re.match(r'^\d+(?:\.\d+)*[.)]\s+', first):
        return first
    return clause.get('section_heading') or ''


def structural_reason(text, heading):
    if not text.strip():
        return 'Empty source passage'
    if text.strip() == heading.strip() or re.fullmatch(r'(?:\d+\.\s*)+[A-Za-z &/\-]+', text.strip()):
        return 'Section heading; retained as source structure'
    if re.fullmatch(r'POL-[A-Z]+-\d+\.\d+\s+[^\n]{1,150}', text.strip()):
        return 'Numbered control heading; retained as source structure'
    if re.fullmatch(r'[^\n]{0,160}(?:Synthetic policy data|Page \d+)[^\n]*(?:\n[^\n]{0,160}){0,3}', text.strip(), re.I):
        return 'Page header/footer; retained as source structure'
    if re.match(r'^(?:Metadata|Policy ID|Status|Version|Owner|Effective date|Review date|Approval date|Approver|Term|Role|Test|Scenario)\s*\|', text, re.I):
        return 'Metadata or table header; retained as source structure'
    return None


def build_taxonomy(documents, clauses, schema_concepts=()):
    by_document = defaultdict(list)
    for clause in clauses:
        by_document[clause['policy_id']].append(clause)
    assignments, coverage, inventory, section_rows = [], [], [], []
    used = defaultdict(set)
    facet_evidence = defaultdict(list)
    vocabulary = []
    for kind, entries in [('CATEGORY', CATEGORIES), ('TOPIC', TOPICS)]:
        for key, label, definition, aliases in entries:
            vocabulary.append({'concept_id': f'PTX-{kind}-{key}', 'preferred_name': label,
                'kind': kind, 'definition': definition, 'inclusion_criteria': 'Explicit source occurrence of: ' + '; '.join(aliases),
                'exclusion_criteria': 'No inferred applicability, numerical requirement or semantic equivalence; ambiguous meanings require review.',
                'aliases': aliases, 'vocabulary_origin': 'CURATED_CLASSIFICATION_VOCABULARY', 'review_status': 'PROPOSED'})
    for doc in documents:
        rows = sorted(by_document[doc['policy_id']], key=lambda c: (c.get('sequence', 0), str(c['id'])))
        synthetic = str(doc.get('source_type', '')).lower() in ('manufactured', 'synthetic') or any(
            re.search(r'synthetic (?:training|policy|demonstration)|fictional', c['source_excerpt'], re.I) for c in rows)
        current = bool(doc.get('policy_version_id')) and str(doc.get('catalog_version', doc.get('version'))) == str(doc.get('version'))
        inventory.append({**doc, 'synthetic': synthetic, 'source_passages': len(rows),
            'source_status': 'CURRENT' if current and rows else 'MISSING_OR_OUTDATED_SOURCE',
            'content_digest': hashlib.sha256(json.dumps([(c['id'], c['source_excerpt']) for c in rows], ensure_ascii=False).encode()).hexdigest()})
        for clause in rows:
            text = clause['source_excerpt']
            heading = heading_for(clause)
            cid = 'CPI-CLAUSE-' + str(clause['id'])
            source = {'document_id': 'CPI-POLICY-' + str(doc['policy_id']), 'document_name': doc['title'],
                'policy_id': doc['policy_id'], 'policy_version_id': doc.get('policy_version_id'),
                'version': str(doc.get('version') or 'UNKNOWN'), 'checksum': doc.get('checksum'),
                'clause_id': cid, 'clause': clause.get('clause_number'), 'section': heading or None,
                'page': clause.get('page_number'), 'sequence': clause.get('sequence'), 'passage': text,
                'synthetic': synthetic, 'origin': 'CPI_CURRENT_POLICY_SOURCE'}
            content_role = 'TRAINING_MATERIAL' if matches(heading, ['training and evaluation', 'training scenarios', 'training prompts']) else 'POLICY_CONTENT'
            if heading:
                section_rows.append({'clause_id': cid, 'policy_id': doc['policy_id'], 'section': heading})
            reason = structural_reason(text, heading)
            disposition = 'STRUCTURE' if reason else 'UNCLASSIFIED'
            facets = {key: [] for key in FACETS}
            if not reason and current:
                for key, entries in FACETS.items():
                    for label, aliases in entries:
                        hits = matches(text, aliases)
                        if hits:
                            evidence = {'dimension': key, 'value': label, 'matches': hits, 'source': source,
                                'status': 'PROPOSED', 'meaning': 'Explicit mention, not approved policy scope'}
                            facet_evidence[(key, label)].append(evidence)
                            facets[key].append(label)
                # An explicit section heading provides primary classification. If it
                # is generic, retain every supported category in the passage.
                category_hits = [(entry, matches(heading, entry[3]), 'SECTION') for entry in CATEGORIES]
                category_hits = [h for h in category_hits if h[1]]
                if not category_hits:
                    category_hits = [(entry, matches(text, entry[3]), 'PASSAGE') for entry in CATEGORIES]
                    category_hits = [h for h in category_hits if h[1]]
                topics = [(entry, matches(text, entry[3])) for entry in TOPICS]
                topics = [(entry, hits) for entry, hits in topics if hits]
                for category, hits, location in category_hits:
                    # Category-only assignments are useful and do not fabricate a topic.
                    for topic, topic_hits in topics or [(None, [])]:
                        area = facets['policy_area'][0] if len(facets['policy_area']) == 1 else ('Multiple areas mentioned' if facets['policy_area'] else 'Unspecified area')
                        product = facets['product'][0] if len(facets['product']) == 1 else ('Multiple products mentioned' if facets['product'] else 'Unspecified product')
                        path = ['Credit risk', area, product, category[1]] + ([topic[1]] if topic else [])
                        aid = identifier(VERSION, doc['policy_id'], doc.get('policy_version_id'), cid, category[0], topic[0] if topic else '')
                        assignments.append({'assignment_id': aid, 'clause_id': cid, 'category_id': 'PTX-CATEGORY-' + category[0],
                            'topic_id': 'PTX-TOPIC-' + topic[0] if topic else None, 'path': path,
                            'category': category[1], 'topic': topic[1] if topic else None,
                            'facets': facets, 'content_role': content_role, 'category_evidence': hits, 'category_evidence_location': location,
                            'topic_evidence': topic_hits, 'source': source, 'status': 'PROPOSED',
                            'method': 'Literal controlled vocabulary; section-first classification',
                            'interpretation': 'Passage-level co-occurrence; does not assert a product-specific rule or applicability'})
                        used['PTX-CATEGORY-' + category[0]].add(cid)
                        if topic:
                            used['PTX-TOPIC-' + topic[0]].add(cid)
                if category_hits:
                    disposition = 'CLASSIFIED'
                else:
                    reason = 'No supported category match; human classification required'
            if not current:
                disposition, reason = 'UNCLASSIFIED', 'Source version does not match current policy catalog'
            coverage.append({'clause_id': cid, 'policy_id': doc['policy_id'], 'disposition': disposition,
                'reason': reason, 'facets': facets, 'content_role': 'STRUCTURE' if disposition == 'STRUCTURE' else content_role, 'source': source})
    # Exact workbook labels are reference candidates only, never executable field bindings.
    for concept in vocabulary:
        concept['support_count'] = len(used[concept['concept_id']])
        concept['supporting_clause_ids'] = sorted(used[concept['concept_id']])
        concept['support_status'] = 'SOURCE_SUPPORTED' if concept['support_count'] else 'NOT_OBSERVED'
        labels = {a.casefold() for a in [concept['preferred_name'], *concept['aliases']]}
        concept['schema_references'] = [{'concept_id': s['concept_id'], 'preferred_name': s['preferred_name'],
            'source_entity': s.get('metadata', {}).get('source_entity'), 'status': 'REFERENCE_ONLY'}
            for s in schema_concepts if s.get('kind') == 'ATTRIBUTE' and s['preferred_name'].casefold() in labels]
    tree = {}
    for a in assignments:
        parent = None
        for level, label in enumerate(a['path']):
            nid = identifier(*a['path'][:level + 1])
            node = tree.setdefault(nid, {'node_id': nid, 'parent_id': parent, 'label': label,
                'level': level, 'path': a['path'][:level + 1], 'status': 'PROPOSED', 'clause_ids': set()})
            node['clause_ids'].add(a['clause_id'])
            parent = nid
    nodes = [{**n, 'clause_ids': sorted(n['clause_ids']), 'support_count': len(n['clause_ids'])} for n in tree.values()]
    counts = Counter(c['disposition'] for c in coverage)
    digest = hashlib.sha256(json.dumps({'version': VERSION, 'vocabulary': [CATEGORIES, TOPICS, FACETS],
        'sources': [(d['policy_id'], d.get('policy_version_id'), d.get('checksum'), d['content_digest'], d['source_status']) for d in inventory]},
        sort_keys=True, default=str).encode()).hexdigest()
    return {'version': VERSION, 'source_digest': digest, 'review_status': 'PROPOSED',
        'methodology': [
            'Curated controlled vocabulary; branches and assignments are materialized only from current source occurrences.',
            'Credit risk is the configured project domain. Policy area, product, segment and geography require literal passage evidence.',
            'Section headings select categories first; generic sections use literal passage matches. Topics are co-occurring terms, not extracted requirements.',
            'Training and evaluation sections are labelled TRAINING_MATERIAL and kept distinct from policy content.',
            'Multiple products/areas remain explicitly multiple; no cartesian combination or inherited document-wide scope is invented.',
            'Every stored current passage is classified, retained as structure or listed as unclassified. This is stored-text coverage, not OCR/page completeness.',
            'Assignments and vocabulary remain proposed. They do not approve policy scope, rules, ontology or executable field mappings.',
            'Unobserved vocabulary remains visible as NOT_OBSERVED and is excluded from the observed tree.',
            'Synthetic source labels are preserved, including imported documents labelled synthetic in their content.',
        ], 'summary': {'policies': len(inventory), 'source_passages': len(coverage),
            'classified_passages': counts['CLASSIFIED'], 'structure_passages': counts['STRUCTURE'],
            'unclassified_passages': counts['UNCLASSIFIED'], 'assignments': len(assignments), 'tree_nodes': len(nodes),
            'supported_concepts': sum(c['support_count'] > 0 for c in vocabulary),
            'unobserved_concepts': sum(c['support_count'] == 0 for c in vocabulary),
            'missing_source_policies': sum(d['source_status'] != 'CURRENT' for d in inventory)},
        'documents': inventory, 'dictionary': vocabulary, 'tree': nodes, 'assignments': assignments,
        'facets': [{'dimension': key[0], 'value': key[1], 'support_count': len(items), 'status': 'PROPOSED',
            'evidence': items} for key, items in sorted(facet_evidence.items())],
        'coverage': coverage, 'source_sections': section_rows}


def current_taxonomy(connection_factory, schema_concepts=()):
    return build_taxonomy(*source_rows(connection_factory), schema_concepts=schema_concepts)
