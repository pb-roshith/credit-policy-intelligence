import copy
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from app.risk_knowledge.repositories import SQLiteRepository
from app.risk_knowledge.semantic_extraction import (ExtractedRule, validate_rule, taxonomy_context,
    assemble_graph, relevant_rules, restore_source_wrapping, rule_id, numeric_values, approved_rules, quantity_supported)
from app.risk_knowledge.semantic_pipeline import process_source, current_records, review_rule,resolve_record_references,seal
from app.risk_knowledge.semantic_model import validate_instance
from app.risk_knowledge.semantic_view import graph_view

TEXT = 'For salaried borrowers with home loans exceeding 50 lakhs, LTV shall not exceed 75 percent.'
EXCEPTION = 'Exception to the above LTV requirement requires CR approval.'


def fixture():
    policy = {'policy_id': 1, 'title': 'Example credit policy', 'source_type': 'synthetic'}
    version = {'id': 7, 'version': '1', 'checksum': hashlib.sha256(TEXT.encode()).hexdigest()}
    clauses = [{'id': 1, 'sequence': 1, 'source_excerpt': TEXT, 'section_heading': 'Eligibility', 'page_number': 5},
               {'id': 2, 'sequence': 2, 'source_excerpt': EXCEPTION, 'section_heading': 'Exceptions', 'page_number': 6}]
    rule = ExtractedRule(clause_id=1, rule_sequence=1, name='Maximum home loan LTV', rule_kind='QUANTITATIVE', source_quote=TEXT,
        products=[{'name': 'Home loan', 'evidence': 'home loans'}], customer_segments=[{'name': 'Salaried', 'evidence': 'salaried'}],
        metrics=[{'key': 'ltv', 'name': 'LTV', 'unit': '%', 'evidence': 'LTV'}],
        thresholds=[{'metric_key': 'ltv', 'operator': 'LTE', 'value': 75, 'unit': '%', 'evidence': 'LTV shall not exceed 75 percent'}],
        conditions={'logic': 'AND', 'conditions': [{'field': 'loan_amount', 'operator': 'GT', 'value': 50, 'unit': 'lakh', 'evidence': 'home loans exceeding 50 lakhs'}]},
        taxonomy_ids=['PTX-TOPIC-ltv', 'PTX-CATEGORY-eligibility'])
    exception = ExtractedRule(clause_id=2, rule_sequence=1, name='CR approval for LTV exception', rule_kind='EXCEPTION_RULE', source_quote=EXCEPTION,
        approvals=[{'name': 'CR', 'kind': 'ROLE', 'evidence': 'CR approval'}], base_rule_ref='clause:1:rule:1', reference_quote='above LTV requirement')
    return policy, version, clauses, rule, exception


class SemanticExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.repo = SQLiteRepository(Path(self.temp.name)/'semantic.sqlite3')

    def extract(self, two_batches=False):
        policy, version, clauses, rule, exception = fixture()
        contexts = []
        def provider(context):
            contexts.append(copy.deepcopy(context))
            ids = {c['id'] for c in context['primary_clauses']}
            return {'rules': [r.model_dump() for r in (rule, exception) if r.clause_id in ids],
                'coverage': [{'clause_id': cid, 'disposition': 'RULES', 'reason': 'Explicit requirement'} for cid in ids]}
        if two_batches:
            with patch('app.risk_knowledge.semantic_pipeline.sources_in_batches', lambda rows: [[c] for c in rows]):
                report = process_source(policy, version, clauses, self.repo, provider=provider)
        else: report = process_source(policy, version, clauses, self.repo, provider=provider)
        return report, contexts

    def test_requested_example_preserves_segment_condition_unit_and_threshold(self):
        report, _ = self.extract()
        self.assertEqual(report['rules_approved'], 2)
        records = current_records(self.repo)
        graph = assemble_graph(records)
        self.assertTrue(validate_instance(graph)['conforms'])
        condition = next(n for n in graph['nodes'] if n['type'] == 'Condition')
        self.assertEqual(condition['properties'], {'field': 'loan_amount', 'operator': 'GT', 'value': 50.0, 'unit': 'lakh'})
        threshold = next(n for n in graph['nodes'] if n['type'] == 'Threshold')
        self.assertEqual(threshold['properties']['value'], 75)
        self.assertEqual(threshold['properties']['operator'], 'LTE')
        self.assertTrue(any(e['predicate'] == 'APPLIES_TO_SEGMENT' for e in graph['relationships']))
        self.assertEqual(next(n for n in graph['nodes'] if n['type'] == 'ApprovalAuthority')['label'], 'CR')

    def test_graph_is_context_for_next_batch_and_exception_is_connected(self):
        _, contexts = self.extract(two_batches=True)
        self.assertEqual(contexts[0]['existing_graph_rules'], [])
        self.assertEqual(contexts[1]['existing_graph_rules'][0]['id'], rule_id(7, 1, 1))
        self.assertTrue(contexts[1]['existing_graph_neighborhood']['relationships'])
        graph = assemble_graph(current_records(self.repo))
        self.assertTrue(any(e['predicate'] == 'HAS_EXCEPTION' and e['subject'] == rule_id(7, 1, 1) for e in graph['relationships']))

    def test_relative_reference_does_not_choose_between_multiple_ltv_rules(self):
        self.extract()
        record=current_records(self.repo)[0]
        duplicate=copy.deepcopy(record['rules'][0]);duplicate['id']=rule_id(7,1,2)
        duplicate['extracted']['rule_sequence']=2
        record['rules'].append(duplicate)
        resolve_record_references(record,[])
        exception=next(r for r in record['rules'] if r['extracted']['clause_id']==2)
        self.assertEqual(exception['status'],'PROPOSED')
        self.assertIn('ambiguous',exception['validation_error'])

    def test_automatic_approval_cannot_invent_product_or_currency(self):
        _,_,clauses,rule,_=fixture()
        primary={c['id']:c for c in clauses}
        rule.products[0].name='Credit card'
        reason=validate_rule(rule,primary,primary,set(),{t['id'] for t in taxonomy_context()})
        self.assertIn('not supported',reason)
        rule.products[0].name='Home loan'
        rule.conditions.conditions[0].unit='INR'
        reason=validate_rule(rule,primary,primary,set(),{t['id'] for t in taxonomy_context()})
        self.assertIn('Currency',reason)

    def test_no_repeated_model_call_for_successful_checkpoint(self):
        self.extract()
        policy, version, clauses, _, _ = fixture()
        report = process_source(policy, version, clauses, self.repo, provider=lambda _: self.fail('Completed source batch must be reused'))
        self.assertEqual(report['rules_approved'], 2)

    def test_invalid_reextraction_cannot_replace_a_validated_threshold(self):
        self.extract()
        record=current_records(self.repo)[0]
        record['completed_batches']=[]
        self.repo.put('metadata',record['id'],seal(record))
        policy,version,clauses,rule,exception=fixture()
        rule.thresholds[0].value=85
        process_source(policy,version,clauses,self.repo,provider=lambda _: {'rules':[rule.model_dump(),exception.model_dump()],
            'coverage':[{'clause_id':c['id'],'disposition':'RULES','reason':'Requirements'} for c in clauses]})
        saved=next(r for r in current_records(self.repo)[0]['rules'] if r['id']==rule_id(7,1,1))
        self.assertEqual(saved['status'],'APPROVED')
        self.assertEqual(saved['extracted']['thresholds'][0]['value'],75)
        self.assertTrue(saved['latest_proposal']['validation_error'])

    def test_human_rejection_persists_and_removes_dependent_exception(self):
        self.extract()
        record = current_records(self.repo)[0]
        reviewed = review_rule(self.repo, rule_id(7,1,1), status='REJECTED', notes='Source interpretation rejected', actor='reviewer', expected_digest=record['content_digest'])
        self.assertTrue(reviewed['rules'][0]['human_override'])
        self.assertFalse(approved_rules(current_records(self.repo)))
        self.assertEqual(relevant_rules(current_records(self.repo), 'LTV home loan'), [])
        self.extract()
        self.assertEqual(current_records(self.repo)[0]['rules'][0]['status'], 'REJECTED')

    def test_override_cannot_invent_threshold_or_use_stale_digest(self):
        self.extract()
        record = current_records(self.repo)[0]
        replacement = copy.deepcopy(record['rules'][0]['extracted'])
        replacement['thresholds'][0]['value'] = 85
        with self.assertRaises(ValueError): review_rule(self.repo, rule_id(7,1,1), status='APPROVED', notes='Invalid value', actor='reviewer', expected_digest=record['content_digest'], replacement=replacement)
        with self.assertRaises(ValueError): review_rule(self.repo, rule_id(7,1,1), status='REJECTED', notes='Stale edit', actor='reviewer', expected_digest='stale')

    def test_missing_clause_dispositions_are_not_successful_coverage(self):
        policy, version, clauses, _, _ = fixture()
        result = process_source(policy, version, clauses, self.repo, provider=lambda _: {'rules': [], 'coverage': []})
        self.assertEqual(result['status'], 'Completed with errors')
        self.assertEqual(result['rules_approved'], 0)
        self.assertGreater(result['unresolved_spans'], 0)

    def test_unresolved_antecedent_cannot_become_approved(self):
        policy, version, clauses, _, exception = fixture()
        exception.base_rule_ref = None
        result = process_source(policy, version, clauses, self.repo, provider=lambda _: {'rules': [exception.model_dump()], 'coverage': [{'clause_id': 1, 'disposition': 'NON_RULE', 'reason': 'Context'}, {'clause_id': 2, 'disposition': 'RULES', 'reason': 'Exception'}]})
        self.assertEqual(result['rules_approved'], 0)
        self.assertTrue(result['partial_result'])

    def test_pdf_whitespace_restoration_does_not_change_source_facts(self):
        _, _, clauses, rule, _ = fixture()
        clauses[0]['source_excerpt'] = TEXT.replace('home loans', 'home\nloans')
        primary = {1: clauses[0]}
        restore_source_wrapping(rule, primary, primary)
        self.assertIn('home\nloans', rule.source_quote)
        self.assertIsNone(validate_rule(rule, primary, primary, set(), {t['id'] for t in taxonomy_context()}))

    def test_lakh_scale_is_explicit_and_currency_is_not_invented(self):
        self.assertIn(5000000, numeric_values('50 lakhs'))
        self.assertFalse(quantity_supported(5000000,'lakh','50 lakhs'))
        self.assertTrue(quantity_supported(50,'lakh','50 lakhs'))
        self.assertTrue(quantity_supported(5000000,'INR','INR 50 lakhs'))
        self.extract()
        condition = next(n for n in assemble_graph(current_records(self.repo))['nodes'] if n['type'] == 'Condition')
        self.assertNotIn('currency', condition['properties'])

    def test_graph_starts_small_and_expands_one_hop_with_pagination(self):
        self.extract()
        records = current_records(self.repo)
        overview = graph_view(records)
        self.assertLessEqual(len(overview['nodes']), 6)
        self.assertTrue(all(n['type'] == 'CreditPolicy' for n in overview['nodes']))
        neighborhood = graph_view(records, focus=rule_id(7,1,1), limit=3)
        self.assertLessEqual(len(neighborhood['nodes']), 4)
        self.assertIsNotNone(neighborhood['next_offset'])
        ids = {n['id'] for n in neighborhood['nodes']}
        self.assertTrue(all(e['source'] in ids and e['target'] in ids for e in neighborhood['edges']))


if __name__ == '__main__': unittest.main()
