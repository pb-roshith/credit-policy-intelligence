import copy
import unittest
from unittest.mock import patch
import networkx as nx
from app.risk_knowledge.graph import NetworkXGraphRepository, InMemoryGraphRepository, graph_from_env


class NetworkXGraphTests(unittest.TestCase):
    def setUp(self):
        self.repository = NetworkXGraphRepository()

    def node(self, identifier, kind='ENTITY', status='SOURCE'):
        return {'id':identifier, 'label':identifier, 'type':kind, 'status':status}

    def edge(self, identifier, source, target, predicate='CONTAINS', passage='Exact source wording'):
        return {'id':identifier, 'source':source, 'target':target, 'predicate':predicate,
                'status':'SOURCE', 'provenance':{'document_id':'POLICY-1', 'passage':passage}}

    def test_networkx_is_the_default_backend(self):
        with patch.dict('os.environ', {'NEO4J_URI':''}):
            self.assertIsInstance(graph_from_env(), NetworkXGraphRepository)
        self.assertIs(InMemoryGraphRepository, NetworkXGraphRepository)
        self.assertIsInstance(self.repository._graph, nx.MultiDiGraph)

    def test_parallel_directed_relationships_keep_separate_evidence(self):
        nodes = [self.node('a'), self.node('b')]
        edges = [self.edge('e1','a','b','APPLIES_TO','Passage one'),
                 self.edge('e2','a','b','REQUIRES','Passage two'),
                 self.edge('e3','b','a','OVERRIDES','Passage three')]
        self.repository.replace(nodes, edges)
        self.assertEqual(self.repository._graph.number_of_edges('a','b'),2)
        self.assertEqual(self.repository._graph.number_of_edges('b','a'),1)
        self.assertEqual({e['id']:e for e in self.repository.snapshot()['edges']}, {e['id']:e for e in edges})

    def test_approved_rule_retrieval_requires_correct_direction_and_exact_clause(self):
        nodes = [self.node('approved','PolicyRule','APPROVED'), self.node('candidate','PolicyRule','CANDIDATE'),
                 self.node('governed','GovernedPolicyRule','APPROVED'), self.node('reversed','PolicyRule','APPROVED'),
                 self.node('clause','PolicyClause'), self.node('concept')]
        edges = [self.edge('a','approved','clause','DERIVED_FROM'),
                 self.edge('b','approved','clause','APPLIES_TO'),
                 self.edge('c','candidate','clause','DERIVED_FROM'),
                 self.edge('d','governed','clause','DERIVED_FROM'),
                 self.edge('e','clause','reversed','DERIVED_FROM'),
                 self.edge('f','reversed','concept','DERIVED_FROM')]
        self.repository.replace(nodes, edges)
        self.assertEqual(self.repository.approved_rule_ids(),['approved'])

    def test_neighborhood_explores_incoming_outgoing_links_and_limits_hops(self):
        nodes = [self.node(n) for n in ['a','b','c','d','isolated']]
        edges = [self.edge('ab','a','b'), self.edge('bc','b','c'), self.edge('dc','d','c')]
        self.repository.replace(nodes, edges)
        self.assertEqual(self.repository.neighborhood('b',0),{'b'})
        self.assertEqual(self.repository.neighborhood('b',1),{'a','b','c'})
        self.assertEqual(self.repository.neighborhood('b',2),{'a','b','c','d'})
        self.assertEqual(self.repository.neighborhood('isolated'),{'isolated'})
        self.assertEqual(self.repository.neighborhood('missing'),set())

    def test_cyclic_neighborhood_is_finite(self):
        self.repository.replace([self.node(n) for n in ['a','b','c']],
                                [self.edge('ab','a','b'),self.edge('bc','b','c'),self.edge('ca','c','a')])
        self.assertEqual(self.repository.neighborhood('a',10),{'a','b','c'})

    def test_failed_replacement_preserves_previous_valid_graph(self):
        nodes=[self.node('a'),self.node('b')]
        edge=self.edge('valid','a','b')
        self.repository.replace(nodes,[edge])
        original=self.repository.snapshot()
        for invalid in [edge|{'provenance':{}},edge|{'target':'unknown'}]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.repository.replace(nodes,[invalid])
                self.assertEqual(self.repository.snapshot(),original)

    def test_ambiguous_edge_identity_is_rejected(self):
        edge=self.edge('same','a','b')
        with self.assertRaisesRegex(ValueError,'edge IDs must be unique'):
            self.repository.replace([self.node('a'),self.node('b')],[edge,edge|{'predicate':'REQUIRES'}])

    def test_snapshots_and_caller_inputs_cannot_mutate_graph_evidence(self):
        nodes=[self.node('a'),self.node('b')]
        edges=[self.edge('e','a','b')]
        self.repository.replace(nodes,edges)
        expected=copy.deepcopy(self.repository.snapshot())
        edges[0]['provenance']['passage']='Changed input'
        snapshot=self.repository.snapshot()
        snapshot['edges'][0]['provenance']['passage']='Changed export'
        self.assertEqual(self.repository.snapshot(),expected)

    def test_invalid_neighborhood_depth(self):
        for depth in [-1,True,'2']:
            with self.subTest(depth=depth), self.assertRaises(ValueError):
                self.repository.neighborhood('node',depth)


if __name__=='__main__':unittest.main()
