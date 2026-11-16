from abc import ABC, abstractmethod
from copy import deepcopy
import os
import networkx as nx
from .evaluation import leaves
from .ingestion import uid


class GraphRepository(ABC):
    @abstractmethod
    def replace(self, nodes, edges): ...
    @abstractmethod
    def snapshot(self): ...
    @abstractmethod
    def approved_rule_ids(self): ...
    @abstractmethod
    def neighborhood(self, identifier, depth=2): ...


class NetworkXGraphRepository(GraphRepository):
    """Directed, parallel policy relationships backed by a NetworkX MultiDiGraph."""
    def __init__(self):
        self._graph = nx.MultiDiGraph()

    @property
    def nodes(self):
        return deepcopy(dict(self._graph.nodes(data=True)))

    @property
    def edges(self):
        return deepcopy([data for _, _, data in self._graph.edges(data=True)])

    def replace(self, nodes, edges):
        replacement = nx.MultiDiGraph()
        for node in nodes:
            if node['id'] in replacement:
                raise ValueError('Graph node IDs must be unique')
            replacement.add_node(node['id'], **deepcopy(node))
        edge_ids = set()
        for edge in edges:
            if not edge.get('provenance'):
                raise ValueError('Every graph edge requires provenance')
            if edge['source'] not in replacement or edge['target'] not in replacement:
                raise ValueError('Graph edge endpoint does not exist')
            if edge['id'] in edge_ids:
                raise ValueError('Graph edge IDs must be unique')
            edge_ids.add(edge['id'])
            replacement.add_edge(edge['source'], edge['target'], key=edge['id'], **deepcopy(edge))
        # Publish only a complete, validated graph; failed replacements leave it intact.
        self._graph = replacement

    def snapshot(self):
        return {'nodes': list(self.nodes.values()), 'edges': self.edges}

    def approved_rule_ids(self):
        # Follow directed, provenanced edges to exact source clauses.
        rules = set()
        for clause, attributes in self._graph.nodes(data=True):
            if attributes.get('type') != 'PolicyClause':
                continue
            for source, _, edge in self._graph.in_edges(clause, data=True):
                rule = self._graph.nodes[source]
                if edge['predicate'] == 'DERIVED_FROM' and rule.get('type') == 'PolicyRule' and rule.get('status') == 'APPROVED':
                    rules.add(source)
        return sorted(rules)

    def neighborhood(self, identifier, depth=2):
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
            raise ValueError('Graph neighborhood depth must be a nonnegative integer')
        if identifier not in self._graph:
            return set()
        # Explorer neighborhoods include incoming and outgoing links. Stored edges
        # and approved-rule traversal retain their original directions.
        view = self._graph.to_undirected(as_view=True)
        return set(nx.single_source_shortest_path_length(view, identifier, cutoff=depth))

    def governed_rule_paths(self):
        """Exact policy -> clause <- approved, current governed rule paths."""
        paths = {}
        for rid, node in self._graph.nodes(data=True):
            if node.get('type') != 'GovernedPolicyRule' or node.get('status') not in ('APPROVED', 'ACTIVE'):
                continue
            payload = node.get('payload') or {}
            if payload.get('review_required') or not payload.get('approved_by'):
                continue
            if (payload.get('definition') or {}).get('representation_id'):
                if not payload.get('graph_compilation_verified'):
                    continue
                links=[target for _,target,edge in self._graph.out_edges(rid,data=True)
                       if edge['predicate']=='COMPILED_FROM' and self._graph.nodes[target].get('type')=='PolicyRequirement'
                       and self._graph.nodes[target].get('status') in ('VALIDATED','APPROVED')]
                if len(links)!=1:continue
            for _, clause, edge in self._graph.out_edges(rid, data=True):
                if edge['predicate'] != 'DERIVED_FROM' or self._graph.nodes[clause].get('type') != 'PolicyClause':
                    continue
                for parent, _, contains in self._graph.in_edges(clause, data=True):
                    if contains['predicate'] == 'CONTAINS' and self._graph.nodes[parent].get('type') == 'PolicyDocument':
                        paths[rid] = [parent, clause, rid]
                        if (payload.get('definition') or {}).get('representation_node_id'):
                            paths[rid].append(payload['definition']['representation_node_id'])
        return paths


# Compatibility for existing imports; there is only one in-memory implementation.
InMemoryGraphRepository = NetworkXGraphRepository


class Neo4jGraphRepository(NetworkXGraphRepository):
    """Optional Neo4j mirror of NetworkX; CPI PostgreSQL remains authoritative."""
    def __init__(self, uri, user, password):
        super().__init__()
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver.verify_connectivity()

    def replace(self, nodes, edges):
        super().replace(nodes, edges)
        # This label/namespace is dedicated to this prototype and contains no other app data.
        def write(tx):
            tx.run('MATCH (n:CPIPrototype {namespace:$ns}) DETACH DELETE n', ns='credit-policy-prototype').consume()
            tx.run('UNWIND $nodes AS item CREATE (n:CPIPrototype {namespace:$ns, id:item.id}) SET n.label=item.label, n.type=item.type, n.status=item.status',
                   nodes=nodes, ns='credit-policy-prototype').consume()
            import json
            payload = [e | {'provenance_json': json.dumps(e['provenance'])} for e in edges]
            tx.run('UNWIND $edges AS item MATCH (a:CPIPrototype {namespace:$ns, id:item.source}), (b:CPIPrototype {namespace:$ns, id:item.target}) CREATE (a)-[r:RELATED {predicate:item.predicate, provenance:item.provenance_json}]->(b)',
                   edges=payload, ns='credit-policy-prototype').consume()
        with self.driver.session() as session:
            session.execute_write(write)


def graph_from_env():
    if not os.getenv('NEO4J_URI'):
        return NetworkXGraphRepository()
    return Neo4jGraphRepository(os.environ['NEO4J_URI'], os.getenv('NEO4J_USER', 'neo4j'), os.environ['NEO4J_PASSWORD'])


def build_graph(repo, graph):
    nodes, edges = {}, []
    def node(identifier, label, kind, status, source=None, domain='UNKNOWN', payload=None):
        nodes[identifier] = {'id': identifier, 'label': label, 'type': kind, 'status': status,
                             'risk_domain': domain, 'source_name': source.get('document_name') if source else '',
                             'provenance': source, 'payload': payload}
    def edge(a, p, b, source, status='APPROVED'):
        edges.append({'id': uid('EDGE-', f'{a}|{p}|{b}'), 'source': a, 'predicate': p, 'target': b,
                      'provenance': source, 'status': status})
    for c in repo.all('taxonomy_concepts'):
        node(c['concept_id'], c['preferred_name'], c['kind'], c['status'], c['source'], c['risk_domain'], payload=c)
    for c in repo.all('taxonomy_concepts'):
        if c['parent_concept'] in nodes:
            edge(c['parent_concept'], 'CONTAINS', c['concept_id'], c['source'], c['status'])
    for d in repo.all('documents'):
        p = {'document_id': d['document_id'], 'document_name': d['document_name'], 'origin': 'SYNTHETIC_DEMO' if d['synthetic'] else 'SOURCE_DOCUMENT', 'passage': d['document_name']}
        node(d['document_id'], d['document_name'], 'PolicyDocument' if d['document_type'] == 'policy' else 'SourceDocument', 'SOURCE', p)
    for c in repo.all('taxonomy_concepts'):
        if c['source']['origin'] == 'SOURCE_SCHEMA' and c['kind'] == 'ENTITY' and c['source']['document_id'] in nodes:
            edge(c['source']['document_id'], 'CONTAINS', c['concept_id'], c['source'], 'SOURCE')
    for c in repo.all('clauses'):
        p = c['source']
        node(c['clause_id'], 'Clause ' + (p['clause'] or '?'), 'PolicyClause', 'SOURCE', p, payload=c['raw_text'])
        section_id = uid('SECTION-', c['document_id'] + str(p['section']))
        node(section_id, p['section'] or 'Unsectioned', 'PolicySection', 'SOURCE', p)
        edge(c['document_id'], 'CONTAINS', section_id, p, 'SOURCE')
        edge(section_id, 'CONTAINS', c['clause_id'], p, 'SOURCE')
    from .models import Rule
    for raw in repo.all('policy_rules'):
        r = Rule.model_validate(raw)
        p = r.policy.model_dump()
        node(r.rule_id, r.rule_name, 'PolicyRule', r.status, p, r.risk_domain, r.rule_id)
        edge(r.rule_id, 'DERIVED_FROM', r.clause_id, p, r.status)
        for i, c in enumerate(r.scope + leaves(r.conditions)):
            cid = r.rule_id + ':condition:' + str(i)
            node(cid, f'{c.original_term} {c.operator} {c.value}', 'Condition', r.status, p, r.risk_domain)
            edge(r.rule_id, 'HAS_CONDITION', cid, p, r.status)
            if c.taxonomy_mapping in nodes:
                edge(cid, 'MAPS_TO', c.taxonomy_mapping, p, r.status)
                edge(r.rule_id, 'APPLIES_TO', c.taxonomy_mapping, p, r.status)
        for i, e in enumerate(r.exceptions):
            identifier = r.rule_id + ':exception:' + str(i)
            node(identifier, 'Exception: ' + ', '.join(f'{c.attribute} {c.operator} {c.value}' for c in leaves(e)), 'Exception', r.status, p, r.risk_domain)
            edge(r.rule_id, 'HAS_EXCEPTION', identifier, p, r.status)
        outcome_id = r.rule_id + ':outcome'
        node(outcome_id, r.outcome.action, 'Outcome', r.status, p, r.risk_domain)
        edge(r.rule_id, 'REQUIRES', outcome_id, p, r.status)
        if r.outcome.authority:
            authority = uid('AUTH-', r.outcome.authority)
            node(authority, r.outcome.authority, 'ApprovalAuthority', r.status, p, r.risk_domain)
            edge(outcome_id, 'APPROVED_BY', authority, p, r.status)
    for r in repo.all('ontology_relationships'):
        if r['subject'] in nodes and r['object'] in nodes:
            edge(r['subject'], r['predicate'], r['object'], r['source'], r['status'])
    from .conflicts import discover_conflicts
    for finding in discover_conflicts([Rule.model_validate(r) for r in repo.all('policy_rules')]):
        if finding['kind'] == 'POTENTIAL_POLICY_CONFLICT':
            p = finding['sources'][0] | {'origin': 'DETERMINISTIC_OVERLAP_ANALYSIS',
                                        'supporting_sources': finding['sources'], 'analysis': finding['reason']}
            edge(finding['rules'][0], 'CONFLICTS_WITH', finding['rules'][1], p, 'REQUIRES_REVIEW')
    # Section containment can recur for several clauses; provenance remains the first source clause.
    unique_edges = {e['id']: e for e in reversed(edges)}
    graph.replace(list(nodes.values()), list(unique_edges.values()))
