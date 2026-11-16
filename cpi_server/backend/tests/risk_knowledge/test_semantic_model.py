import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, XSD
from pyshacl import validate
from app.risk_knowledge.semantic_model import (CLASSES, RELATIONSHIPS, VERSION,
    semantic_contract, instance_schema, example_instance, validate_instance)
from app.risk_knowledge.semantic_rdf import CPI, ontology_graph, shapes_graph, instance_graph


def node(data, key):
    return next(n for n in data['nodes'] if n['id'] == 'urn:cpi:example:' + key)


def edges_without(data, subject, predicate):
    data['relationships'] = [r for r in data['relationships'] if not (r['subject'] == 'urn:cpi:example:' + subject and r['predicate'] == predicate)]


class SemanticModelTests(unittest.TestCase):
    def assert_rejected(self, data, code):
        report = validate_instance(data)
        self.assertFalse(report['conforms'], report)
        self.assertIn(code, {e['code'] for e in report['errors']}, report)

    def test_example_conforms_to_schema_and_cross_node_constraints(self):
        Draft202012Validator.check_schema(instance_schema())
        report = validate_instance(example_instance())
        self.assertTrue(report['conforms'], report)
        self.assertEqual(set(CLASSES) - {n['type'] for n in example_instance()['nodes']}, {'Customer'})

    def test_invalid_endpoint_type_is_rejected_without_exception(self):
        data = example_instance()
        next(e for e in data['relationships'] if e['predicate'] == 'SOURCE_IN_VERSION')['object'] = node(data, 'product')['id']
        self.assert_rejected(data, 'TYPED_ENDPOINTS')

    def test_duplicate_ids_and_missing_endpoints(self):
        data = example_instance()
        data['nodes'].append(copy.deepcopy(data['nodes'][0]))
        self.assert_rejected(data, 'UNIQUE_IDS')
        data = example_instance()
        data['relationships'][0]['object'] = 'urn:cpi:example:missing'
        self.assert_rejected(data, 'TYPED_ENDPOINTS')

    def test_missing_required_approval_authority_and_wrong_unit(self):
        data = example_instance()
        edges_without(data, 'approval', 'REQUIRES_APPROVAL_FROM')
        self.assert_rejected(data, 'CARDINALITY')
        data = example_instance()
        node(data, 'threshold')['properties']['unit'] = 'score_points'
        self.assert_rejected(data, 'THRESHOLD_METRIC')

    def test_rule_metric_agrees_with_threshold(self):
        data = example_instance()
        next(e for e in data['relationships'] if e['subject'] == node(data, 'rule')['id'] and e['predicate'] == 'USES_METRIC')['object'] = node(data, 'dti')['id']
        self.assert_rejected(data, 'THRESHOLD_METRIC')

    def test_source_version_and_provenance_are_checked(self):
        data = example_instance()
        node(data, 'passage')['properties']['version'] = '2.0'
        self.assert_rejected(data, 'SOURCE_VERSION')
        data = example_instance()
        node(data, 'rule')['source_refs'] = [node(data, 'product')['id']]
        self.assert_rejected(data, 'SOURCE_REFERENCES')

    def test_effective_date_order_and_actual_date_format(self):
        data = example_instance()
        node(data, 'period')['properties']['end_date'] = '2025-12-31'
        self.assert_rejected(data, 'EFFECTIVE_DATES')
        node(data, 'period')['properties']['start_date'] = '2026-02-30'
        self.assert_rejected(data, 'JSON_SCHEMA')

    def test_examples_cannot_silently_become_source_backed(self):
        data = example_instance()
        data['mode'] = 'SOURCE_BACKED'
        self.assert_rejected(data, 'EXAMPLE_ISOLATION')
        data = example_instance()
        node(data, 'rule')['synthetic'] = False
        self.assert_rejected(data, 'SYNTHETIC_PROVENANCE')

    def test_exception_inverse_and_alternative_kind(self):
        data = example_instance()
        edges_without(data, 'rule', 'HAS_EXCEPTION')
        self.assert_rejected(data, 'EXCEPTION_LINKS')
        data = example_instance()
        node(data, 'alternative')['properties']['rule_kind'] = 'QUALITATIVE'
        self.assert_rejected(data, 'EXCEPTION_LINKS')

    def test_condition_value_types_and_not_cardinality(self):
        data = example_instance()
        node(data, 'condition')['properties'].update(operator='IN', value='SME')
        self.assert_rejected(data, 'JSON_SCHEMA')
        node(data, 'condition')['properties']['value'] = ['SME']
        self.assertTrue(validate_instance(data)['conforms'])
        node(data, 'condition')['properties'].update(operator='EXISTS', value=True)
        self.assert_rejected(data, 'JSON_SCHEMA')
        data = example_instance()
        node(data, 'condition-group')['properties']['logic'] = 'NOT'
        extra = copy.deepcopy(node(data, 'condition'))
        extra['id'] = 'urn:cpi:example:condition-2'
        data['nodes'].append(extra)
        edge = copy.deepcopy(next(e for e in data['relationships'] if e['predicate'] == 'HAS_MEMBER'))
        edge.update(id='urn:cpi:example:additional-member', object=extra['id'])
        data['relationships'].append(edge)
        self.assert_rejected(data, 'CONDITION_LOGIC')

    def test_logical_cycles_are_rejected(self):
        data = example_instance()
        next(e for e in data['relationships'] if e['predicate'] == 'HAS_MEMBER')['object'] = node(data, 'condition-group')['id']
        self.assert_rejected(data, 'CONDITION_LOGIC')

    def test_numeric_threshold_is_not_string_and_unknown_properties_are_rejected(self):
        data = example_instance()
        node(data, 'threshold')['properties']['value'] = '80'
        self.assert_rejected(data, 'JSON_SCHEMA')
        data = example_instance()
        node(data, 'rule')['properties']['unknown'] = True
        self.assert_rejected(data, 'JSON_SCHEMA')

    def test_compiler_contract_is_not_changed_by_schema_generation(self):
        from app.risk_knowledge.policy_ontology import ontology_contract
        original = copy.deepcopy(ontology_contract())
        contract = semantic_contract()
        contract['classes']['PolicyRule']['definition'] = 'edited returned copy'
        self.assertNotEqual(semantic_contract()['classes']['PolicyRule']['definition'], 'edited returned copy')
        self.assertEqual(ontology_contract(), original)


class SemanticRDFTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shapes = shapes_graph()

    def conforms(self, data):
        return validate(instance_graph(data), shacl_graph=self.shapes, inference='none', advanced=True)[0]

    def test_turtle_round_trip_and_shacl_meta_validation(self):
        for rdf in [ontology_graph(), self.shapes, instance_graph(example_instance())]:
            self.assertEqual(len(Graph().parse(data=rdf.serialize(format='turtle'), format='turtle')), len(rdf))
        result, _, text = validate(instance_graph(example_instance()), shacl_graph=self.shapes, inference='none', advanced=True, meta_shacl=True)
        self.assertTrue(result, text)

    def test_rdf_rejects_unit_authority_date_and_source_version_errors(self):
        for key in ['unit', 'authority', 'date', 'version', 'quantitative', 'exception_kind', 'condition_cycle']:
            with self.subTest(key=key):
                data = example_instance()
                if key == 'unit': node(data, 'threshold')['properties']['unit'] = 'score_points'
                if key == 'authority': edges_without(data, 'approval', 'REQUIRES_APPROVAL_FROM')
                if key == 'date': node(data, 'period')['properties']['end_date'] = '2025-12-31'
                if key == 'version': node(data, 'passage')['properties']['version'] = '2.0'
                if key == 'quantitative': edges_without(data, 'rule', 'HAS_THRESHOLD')
                if key == 'exception_kind': node(data, 'alternative')['properties']['rule_kind'] = 'QUALITATIVE'
                if key == 'condition_cycle': next(e for e in data['relationships'] if e['predicate'] == 'HAS_MEMBER')['object'] = node(data, 'condition-group')['id']
                self.assertFalse(self.conforms(data))

    def test_rdf_membership_list_is_valid(self):
        data = example_instance()
        node(data, 'condition')['properties'].update(operator='IN', value=['SME', 'Commercial'])
        self.assertTrue(self.conforms(data))

    def test_borrower_is_customer_but_customer_cannot_use_borrower_only_edges(self):
        data = example_instance()
        node(data, 'borrower')['type'] = 'Customer'
        self.assertFalse(self.conforms(data))
        self.assertFalse(validate_instance(data)['conforms'])

    def test_unreified_relationship_is_rejected(self):
        rdf = instance_graph(example_instance())
        rdf.add((URIRef('urn:cpi:example:rule'), CPI.REQUIRES_APPROVAL, URIRef('urn:cpi:example:approval')))
        result, _, _ = validate(rdf, shacl_graph=self.shapes, inference='none', advanced=True)
        self.assertFalse(result)


class SemanticAPITests(unittest.TestCase):
    def test_authenticated_contract_download_and_validation_without_database(self):
        from app.routers import risk_knowledge as router
        app = FastAPI()
        app.include_router(router.router)
        with TestClient(app) as client:
            self.assertIn(client.get('/api/risk-knowledge/semantic-model').status_code, (401, 403))
        app.dependency_overrides[router.current_user] = lambda: {'user_id': 'reader', 'role': 'credit_analyst'}
        with patch.object(router, 'shared_policy_connection', side_effect=AssertionError('Schema endpoints must not access database')):
            with TestClient(app) as client:
                for path in ['', '/schema', '/example', '/ontology.ttl', '/shapes.ttl']:
                    self.assertEqual(client.get('/api/risk-knowledge/semantic-model' + path).status_code, 200)
                report = client.post('/api/risk-knowledge/semantic-model/validate', json=example_instance())
                self.assertTrue(report.json()['conforms'])
                self.assertFalse(client.post('/api/risk-knowledge/semantic-model/validate', json={}).json()['conforms'])


if __name__ == '__main__':
    unittest.main()
