import copy
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.risk_knowledge.semantic_view import policy_source_view
from app.routers.risk_knowledge import router
from app.security import current_user


class SemanticSourceViewTests(unittest.TestCase):
    def setUp(self):
        self.document = {'policy_id': 14, 'title': 'Spread Grid', 'policy_version_id': 52,
                         'version': '1.7', 'catalog_version': '1.7', 'checksum': 'current'}
        self.clauses = [{'id': i, 'policy_id': 14, 'policy_version_id': 52, 'sequence': i,
                         'source_excerpt': text, 'page_number': i, 'section_heading': 'Pricing'}
                        for i, text in enumerate(['Maximum spread is 5%.', 'Exceptions require approval.', 'Background.'], 1)]
        self.record = {'policy_version_id': 52, 'source_checksum': 'current', 'rules': [
            {'id': 'r1', 'status': 'APPROVED', 'extracted': {'clause_id': 1,
                'source_quote': 'Maximum spread is 5%.', 'supporting_sources': []}},
            {'id': 'r2', 'status': 'PROPOSED', 'extracted': {'clause_id': 2,
                'source_quote': 'Exceptions require approval.',
                'supporting_sources': [{'clause_id': 1, 'quote': 'Maximum spread is 5%.'}]}}],
            'coverage': [{'clause_id': i, 'disposition': disposition, 'reason': 'Source retained'}
                         for i, disposition in [(1, 'RULES'), (2, 'UNRESOLVED'), (3, 'NON_RULE')]]}

    def test_exact_sources_primary_support_and_proposed_are_visible(self):
        result = policy_source_view(self.document, self.clauses, self.record, {'r1'})
        self.assertEqual(result['summary']['source_passages'], 3)
        self.assertEqual(result['summary']['extracted_rules'], 2)
        self.assertEqual(result['summary']['published_rules'], 1)
        self.assertEqual(result['summary']['proposed_rules'], 1)
        self.assertFalse(result['summary']['complete'])
        self.assertEqual(result['passages'][0]['primary_rule_ids'], ['r1'])
        self.assertEqual(result['passages'][0]['supporting_rule_ids'], ['r2'])
        self.assertEqual(result['passages'][0]['source']['passage'], self.clauses[0]['source_excerpt'])
        self.assertEqual(result['passages'][0]['source']['page'], 1)
        self.assertTrue(all(r['source_quote_verified'] and r['supporting_quotes_verified'] for r in result['rules']))

    def test_source_visible_without_any_extraction(self):
        result = policy_source_view(self.document, self.clauses)
        self.assertFalse(result['has_extraction'])
        self.assertEqual(result['summary']['unprocessed_passages'], 3)
        self.assertEqual(result['rules'], [])

    def test_history_and_other_policies_never_leak_into_current_view(self):
        clauses = self.clauses + [{**self.clauses[0], 'id': 99, 'policy_version_id': 51},
                                  {**self.clauses[0], 'id': 100, 'policy_id': 15}]
        for field, value in [('policy_version_id', 51), ('source_checksum', 'old')]:
            with self.subTest(field=field):
                record = {**self.record, field: value}
                result = policy_source_view(self.document, clauses, record)
                self.assertEqual(len(result['passages']), 3)
                self.assertFalse(result['has_extraction'])
                self.assertEqual(result['rules'], [])
        outdated = {**self.document, 'catalog_version': '2'}
        self.assertFalse(policy_source_view(outdated, clauses, self.record)['has_extraction'])

    def test_mismatched_rule_quotations_are_flagged(self):
        record = copy.deepcopy(self.record)
        record['rules'][0]['extracted']['source_quote'] = 'Invented text'
        record['rules'][1]['extracted']['supporting_sources'][0]['quote'] = 'Invented context'
        result = policy_source_view(self.document, self.clauses, record)
        self.assertFalse(result['rules'][0]['source_quote_verified'])
        self.assertFalse(result['rules'][1]['supporting_quotes_verified'])

    def test_endpoint_shows_sources_without_legacy_build_and_requires_auth(self):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            self.assertIn(client.get('/api/risk-knowledge/semantic-policies/14/representation').status_code, (401, 403))
            app.dependency_overrides[current_user] = lambda: {'user_id': 'reader', 'role': 'credit_analyst'}
            with patch('app.risk_knowledge.policy_taxonomy.source_rows', return_value=([self.document], self.clauses)), \
                 patch('app.risk_knowledge.semantic_pipeline.current_records', return_value=[]), \
                 patch('app.routers.risk_knowledge.semantic_repository'), \
                 patch('app.routers.risk_knowledge.current_representation', side_effect=AssertionError('Legacy build must not be read')):
                response = client.get('/api/risk-knowledge/semantic-policies/14/representation')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['summary']['source_passages'], 3)
                self.assertEqual(client.get('/api/risk-knowledge/semantic-policies/999/representation').status_code, 404)
