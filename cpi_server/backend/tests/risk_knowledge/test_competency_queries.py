import json
import os
from contextlib import contextmanager, ExitStack
from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from app.config import SEED_OUTPUTS_DIR
from app.risk_knowledge.competency_projection import effective_start
from app.risk_knowledge.competency_queries import answer, version_on
from app.risk_knowledge.semantic_model import validate_instance
from app.services.semantic_matching import GraphMatcher, comparison


class PolicyCompetencyTests(TestCase):
    @classmethod
    def setUpClass(cls):
        path = SEED_OUTPUTS_DIR / 'extracted-knowledge' / 'policy-rule-knowledge.json'
        records = json.loads(path.read_bytes())
        documents = [{'policy_id': r['policy_id'], 'title': r['policy_name'],
                      'policy_version_id': r['policy_version_id'], 'effective_date': effective_start(r)[0]} for r in records]
        cls.matcher = GraphMatcher(records, documents, [c for r in records for c in r['source_clauses']])

    def test_current_corpus_answers_have_real_paths_and_quotes(self):
        self.assertTrue(validate_instance(self.matcher.graph)['conforms'])
        self.assertEqual(len(self.matcher.records), 35)
        for question, value in [('industry', 'Hospitality'), ('industry', 'Tier 1'),
                                ('geography', 'foreign jurisdiction'), ('product', 'CRE loans'),
                                ('product', 'Construction Loan'), ('rating', ''), ('exposure', ''),
                                ('collateral', ''), ('breach_approval', ''), ('exceptions', '')]:
            with self.subTest(question=question, value=value):
                result = answer(self.matcher, question, value, limit=1)
                self.assertGreater(result['total'], 0)
                self.assertTrue(result['results'][0].get('source_quote') or result['results'][0].get('scope_sources'))

    def test_scope_preserves_semantics_and_missing_sources(self):
        self.assertEqual(answer(self.matcher, 'industry', 'Commercial Real Estate')['total'], 0)
        self.assertGreater(answer(self.matcher, 'product', 'CRE loans')['total'], 0)
        self.assertIsNone(comparison('India', 'EQ', 'foreign jurisdiction', 'geography'))
        self.assertTrue(comparison('India', 'IN', ['India', 'foreign jurisdiction'], 'geography'))
        self.assertIsNone(comparison('foreign jurisdiction', 'EQ', 'India', 'geography'))
        self.assertIsNone(comparison('unrated', 'LT', 'BBB-', 'ordered_rating'))
        self.assertTrue(comparison('BB+', 'LT', 'BBB-', 'ordered_rating'))
        self.assertFalse(comparison('A-', 'LT', 'BBB-', 'ordered_rating'))

    def test_classification_and_explicit_derivation_are_separate(self):
        rows = answer(self.matcher, 'relationship', 'CLASSIFIED_AS')
        self.assertGreater(rows['total'], 0)
        rule = answer(self.matcher, 'policy_class', rows['results'][0]['id'])['results'][0]
        self.assertTrue(rule['policy_classes'])
        self.assertFalse(rule['derived_from_classes'])

    def test_construction_cap_deviation_requires_both_stated_approvers(self):
        rules = answer(self.matcher, 'exceptions', policy_id=16)['results']
        cap = next(row for row in rules if 'Maximum Exposure Limit per Single Construction Loan' == row['label'])
        self.assertTrue(cap['exception_ids'])
        self.assertEqual({role for item in cap['approvals'] if item['triggered_by_breach']
                          for role in item['authorities']}, {'CLC', 'CCO'})

    def test_rule_versions_require_unambiguous_effective_dates(self):
        old = {'id': 1, 'effective_date': '2025-01-01'}
        new = {'id': 2, 'effective_date': '2026-06-01'}
        self.assertEqual(version_on([old, new], date(2026, 5, 31)), (old, None))
        self.assertEqual(version_on([old, new], date(2026, 6, 1)), (new, None))
        self.assertIsNone(version_on([old, new, {**new, 'id': 3}], date(2026, 6, 1))[0])


@skipUnless(os.getenv('RUN_RISK_KNOWLEDGE_DB_TESTS') == '1', 'Enable transactional policy upload test')
class PolicyUploadDatabaseTests(TestCase):
    def test_stage_compare_queue_and_archive_a_revision(self):
        from app.database import shared_policy_connection
        from app.routers.rules import enqueue_inventory
        from app.risk_knowledge.repositories import PostgreSQLRepository
        from app.risk_knowledge.semantic_pipeline import process_source
        from app.risk_knowledge.semantic_extraction import normative_clause
        from app.services.policy_ingestion import ingest_policy
        from app.services.policy_uploads import stage_policy_upload

        connection = shared_policy_connection()
        key = uuid4().hex
        actor = {'user_id': 'risk_upload_test_' + key, 'role': 'credit_analyst'}

        @contextmanager
        def shared():
            yield connection

        def upload(amount, version, start, policy_id=None):
            text = f'Effective date: {start.isoformat()}\n\nExposure shall not exceed {amount} USD.'
            return stage_policy_upload(UploadFile(file=BytesIO(text.encode()), filename='policy.txt'),
                                       owner=actor['user_id'], policy_id=policy_id, code='TEST-RK-' + key,
                                       title='Upload verification', version=version, effective_date=start)

        def process(policy_id, amount):
            policy, version, _, clauses = ingest_policy(policy_id)
            repo = PostgreSQLRepository(shared, actor['user_id'])

            def provider(context):
                source = next(c for c in context['primary_clauses'] if str(amount) in c['source_excerpt'] and normative_clause(c))
                quote = source['source_excerpt']
                return {'rules': [{'clause_id': source['id'], 'rule_sequence': 1, 'name': 'USD exposure cap',
                    'rule_kind': 'QUANTITATIVE', 'source_quote': quote,
                    'metrics': [{'key': 'exposure', 'name': 'Exposure', 'unit': 'USD', 'evidence': quote}],
                    'thresholds': [{'metric_key': 'exposure', 'operator': 'LTE', 'value': amount, 'unit': 'USD', 'evidence': quote}]}],
                    'coverage': [{'clause_id': c['id'], 'disposition': 'RULES' if c == source else 'NON_RULE',
                                  'reason': 'Source fixture'} for c in context['primary_clauses']]}

            process_source(policy, version, clauses, repo, provider=provider)
            return version

        try:
            with ExitStack() as stack:
                directory = Path(stack.enter_context(TemporaryDirectory()))
                for module in ('app.services.policy_uploads', 'app.services.policy_ingestion'):
                    stack.enter_context(patch(module + '.BASE_DIR', directory))
                    stack.enter_context(patch(module + '.shared_policy_connection', shared))
                stack.enter_context(patch('app.routers.rules.shared_policy_connection', shared))
                stack.enter_context(patch('app.routers.rules.MISTRAL_API_KEY', 'fixture'))
                first = upload(100, '1', date(2025, 1, 1))
                self.assertFalse(connection.execute('SELECT 1 FROM policy_documents WHERE policy_code=%s',
                                                    ('TEST-RK-' + key,)).fetchone())
                with self.assertRaises(HTTPException) as error:
                    enqueue_inventory({**actor, 'user_id': 'another-account'}, staged_upload=first['upload_id'])
                self.assertEqual(error.exception.status_code, 404)
                job = enqueue_inventory(actor, staged_upload=first['upload_id'])
                self.assertEqual(enqueue_inventory(actor, staged_upload=first['upload_id'])['id'], job['id'])
                policy_id = job['policy_ids'][0]
                one = process(policy_id, 100)
                connection.execute("UPDATE rule_inventory_jobs SET status='Completed' WHERE id=%s", (job['id'],))
                second = upload(200, '2', date(2026, 1, 1), policy_id)
                self.assertTrue(second['previous_source_available'])
                self.assertEqual(second['changes']['added'], 2)
                enqueue_inventory(actor, staged_upload=second['upload_id'])
                two = process(policy_id, 200)
                old = connection.execute("""SELECT payload FROM risk_knowledge_objects WHERE kind='metadata'
                    AND payload->>'kind'='semantic_policy_history' AND payload->>'policy_version_id'=%s""", (str(one['id']),)).fetchone()
                self.assertEqual(old['payload']['rules'][0]['extracted']['thresholds'][0]['value'], 100)
                self.assertNotEqual(one['id'], two['id'])
        finally:
            connection.rollback()
            connection.close()
