import copy
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.risk_knowledge.policy_taxonomy import build_taxonomy, matches


def corpus():
    docs = [{'policy_id': 1, 'title': 'Retail lending', 'policy_version_id': 7,
        'version': '1', 'catalog_version': '1', 'checksum': 'source-v1', 'source_type': 'uploaded'}]
    texts = [
        ('1. Eligibility', 'For retail home loans to salaried customers in India, the LTV ceiling is 80%.'),
        ('2. Exceptions', 'For mortgages and auto loans, an exception requires approval.'),
        ('3. Context', 'This paragraph has no known classification words.'),
        ('4. Definitions', '4. Definitions'),
        ('5. Monitoring', 'Monitor portfolio trends quarterly.'),
    ]
    clauses = [{'id': i, 'policy_id': 1, 'sequence': i, 'policy_version_id': 7,
        'source_excerpt': text, 'section_heading': heading, 'page_number': i} for i, (heading, text) in enumerate(texts, 1)]
    return docs, clauses


class PolicyTaxonomyTests(unittest.TestCase):
    def test_hierarchy_is_source_backed_and_does_not_invent_scope(self):
        result = build_taxonomy(*corpus())
        ltv = next(a for a in result['assignments'] if a['topic'] == 'LTV')
        self.assertEqual(ltv['path'], ['Credit risk', 'Retail', 'Home loan', 'Eligibility', 'LTV'])
        self.assertEqual(ltv['facets']['geography'], ['India'])
        self.assertEqual(ltv['facets']['customer_segment'], ['Salaried'])
        for node in result['tree']:
            self.assertTrue(node['clause_ids'])
            self.assertEqual(node['support_count'], len(set(node['clause_ids'])))
        self.assertTrue(all(a['status'] == 'PROPOSED' for a in result['assignments']))
        for a in result['assignments']:
            for hit in a['topic_evidence']:
                self.assertEqual(a['source']['passage'][hit['start']:hit['end']], hit['quote'])

    def test_coverage_reconciles_and_unmatched_content_is_visible(self):
        result = build_taxonomy(*corpus())
        s = result['summary']
        self.assertEqual(s['source_passages'], 5)
        self.assertEqual(s['classified_passages'] + s['unclassified_passages'] + s['structure_passages'], 5)
        self.assertEqual(s['unclassified_passages'], 1)
        self.assertEqual(s['structure_passages'], 1)
        self.assertEqual(len({r['clause_id'] for r in result['coverage']}), 5)

    def test_multiple_products_do_not_generate_cartesian_paths(self):
        result = build_taxonomy(*corpus())
        assignments = [a for a in result['assignments'] if a['clause_id'] == 'CPI-CLAUSE-2']
        self.assertTrue(assignments)
        self.assertTrue(all(a['path'][2] == 'Multiple products mentioned' for a in assignments))
        self.assertTrue(all(not a['facets']['geography'] for a in assignments))
        # The first passage's Retail/India/Salaried values never leak to other passages.
        self.assertTrue(all(a['path'][1] == 'Unspecified area' for a in assignments))

    def test_unused_vocabulary_is_not_shown_as_observed(self):
        result = build_taxonomy(*corpus())
        bureau = next(c for c in result['dictionary'] if c['concept_id'] == 'PTX-TOPIC-bureau')
        self.assertEqual(bureau['support_status'], 'NOT_OBSERVED')
        self.assertFalse(any(n['label'] == 'Bureau score' for n in result['tree']))

    def test_synthetic_detection_and_source_version_changes(self):
        docs, clauses = corpus()
        clauses[2]['source_excerpt'] = 'Status | Synthetic training document'
        a = build_taxonomy(docs, clauses)
        self.assertTrue(a['documents'][0]['synthetic'])
        self.assertTrue(all(r['source']['synthetic'] for r in a['coverage']))
        changed = copy.deepcopy(clauses)
        changed[0]['source_excerpt'] += ' Updated.'
        self.assertNotEqual(a['source_digest'], build_taxonomy(docs, changed)['source_digest'])
        docs[0]['catalog_version'] = '2'
        stale = build_taxonomy(docs, clauses)
        self.assertFalse(stale['assignments'])
        self.assertEqual(stale['summary']['missing_source_policies'], 1)

    def test_schema_similarity_does_not_create_a_binding(self):
        schema = [{'kind': 'ATTRIBUTE', 'concept_id': 'FIELD-1', 'preferred_name': 'LTV', 'metadata': {'source_entity': 'Fact_Loan'}},
            {'kind': 'ATTRIBUTE', 'concept_id': 'FIELD-2', 'preferred_name': 'LTV adjusted', 'metadata': {}}]
        result = build_taxonomy(*corpus(), schema_concepts=schema)
        ltv = next(c for c in result['dictionary'] if c['concept_id'] == 'PTX-TOPIC-ltv')
        self.assertEqual([s['concept_id'] for s in ltv['schema_references']], ['FIELD-1'])
        self.assertEqual(ltv['schema_references'][0]['status'], 'REFERENCE_ONLY')

    def test_word_boundaries_and_pdf_wrapping(self):
        self.assertFalse(matches('capitalization unrelated', ['capital']))
        self.assertTrue(matches('loan to\nvalue', ['loan to value']))

    def test_training_content_is_separate_and_number_in_body_is_not_a_heading(self):
        docs, clauses = corpus()
        clauses[0]['section_heading'] = '11. GenAI Training and Evaluation Requirements'
        clauses[0]['source_excerpt'] = '10 (highest risk) is an example LTV classification.'
        result = build_taxonomy(docs, clauses)
        assignments = [a for a in result['assignments'] if a['clause_id'] == 'CPI-CLAUSE-1']
        self.assertTrue(assignments)
        self.assertTrue(all(a['content_role'] == 'TRAINING_MATERIAL' for a in assignments))
        self.assertTrue(all(a['category'] in ('Training and evaluation', 'AI governance') for a in assignments))

    def test_order_is_repeatable_and_inputs_are_unchanged(self):
        docs, clauses = corpus()
        originals = copy.deepcopy((docs, clauses))
        first = build_taxonomy(docs, clauses)
        self.assertEqual(first, build_taxonomy(docs, clauses))
        self.assertEqual(originals, (docs, clauses))


class PolicyTaxonomyAPITests(unittest.TestCase):
    def test_authentication_and_read_only_policy_filter(self):
        from app.routers import risk_knowledge as router
        from app.security import current_user
        app = FastAPI()
        app.include_router(router.router)
        with TestClient(app) as client:
            self.assertIn(client.get('/api/risk-knowledge/policy-taxonomy').status_code, (401, 403))
        app.dependency_overrides[current_user] = lambda: {'user_id': 'reviewer', 'role': 'credit_analyst'}
        with patch('app.risk_knowledge.policy_taxonomy.source_rows', return_value=corpus()), patch.object(router, 'PostgreSQLRepository') as repo:
            repo.return_value.all.return_value = []
            with TestClient(app) as client:
                response = client.get('/api/risk-knowledge/policy-taxonomy?policy_id=1')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['summary']['source_passages'], 5)
                self.assertEqual(client.get('/api/risk-knowledge/policy-taxonomy?policy_id=99').status_code, 404)
                repo.return_value.put.assert_not_called()
                repo.return_value.put_many.assert_not_called()


if __name__ == '__main__':
    unittest.main()
