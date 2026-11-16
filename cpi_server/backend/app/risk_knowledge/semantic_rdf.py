"""OWL/RDFS model, SHACL constraints and RDF instance serialization.

All artifacts are generated from the business contract. Direct triples support
queries; reified assertions retain per-relationship status and exact evidence.
"""
from collections import defaultdict
from rdflib import Graph, Namespace, URIRef, BNode, Literal
from rdflib.collection import Collection
from rdflib.namespace import RDF, RDFS, OWL, XSD, SH
from .semantic_model import (NAMESPACE, VERSION, CLASSES, RELATIONSHIPS,
                             class_lineage, class_properties)

CPI = Namespace(NAMESPACE)
PREFIXES = f'PREFIX cpi: <{NAMESPACE}>\nPREFIX rdf: <{RDF}>\nPREFIX xsd: <{XSD}>\n'


def graph():
    result = Graph()
    for prefix, namespace in [('cpi', CPI), ('rdf', RDF), ('rdfs', RDFS), ('owl', OWL), ('xsd', XSD), ('sh', SH)]:
        result.bind(prefix, namespace)
    return result


def rdf_list(result, values):
    head = BNode()
    Collection(result, head, values)
    return head


def union(result, names):
    if len(names) == 1:
        return CPI[names[0]]
    node = BNode()
    result.add((node, RDF.type, OWL.Class))
    result.add((node, OWL.unionOf, rdf_list(result, [CPI[n] for n in names])))
    return node


def datatype(spec):
    if spec.get('format') == 'date':
        return XSD.date
    return {'string': XSD.string, 'number': XSD.decimal, 'integer': XSD.integer, 'boolean': XSD.boolean}.get(spec.get('type'))


def literal(value, spec=None):
    kind = datatype(spec or {})
    if kind is None:
        kind = XSD.boolean if isinstance(value, bool) else XSD.decimal if isinstance(value, (int, float)) else XSD.string
    return Literal(value if kind == XSD.boolean else str(value), datatype=kind)


def ontology_graph():
    result = graph()
    root = URIRef(NAMESPACE.rstrip(':'))
    result.add((root, RDF.type, OWL.Ontology))
    result.add((root, OWL.versionInfo, Literal(VERSION)))
    result.add((root, OWL.versionIRI, URIRef(NAMESPACE + VERSION)))
    result.add((root, RDFS.label, Literal('CPI credit policy business ontology')))
    result.add((root, RDFS.comment, Literal('Current semantic schema for source-backed policy knowledge. Business approval remains explicit. Closed-world validation is specified separately in SHACL.')))
    property_domains = defaultdict(list)
    for name, definition in CLASSES.items():
        subject = CPI[name]
        result.add((subject, RDF.type, OWL.Class))
        result.add((subject, RDFS.label, Literal(definition['label'])))
        result.add((subject, RDFS.comment, Literal(definition['definition'])))
        if definition['parent']:
            result.add((subject, RDFS.subClassOf, CPI[definition['parent']]))
        props, _ = class_properties(name)
        for key, spec in props.items():
            property_domains[key].append((name, spec))
    for key, entries in property_domains.items():
        subject = CPI[key]
        result.add((subject, RDF.type, OWL.DatatypeProperty if key != 'value' else RDF.Property))
        result.add((subject, RDFS.domain, union(result, [name for name, _ in entries])))
        spec = entries[0][1]
        dtype = datatype(spec.get('items', spec))
        if dtype:
            result.add((subject, RDFS.range, dtype))
    for name, definition in RELATIONSHIPS.items():
        subject = CPI[name]
        result.add((subject, RDF.type, OWL.ObjectProperty))
        result.add((subject, RDFS.label, Literal(definition['label'])))
        result.add((subject, RDFS.comment, Literal(definition['definition'])))
        result.add((subject, RDFS.domain, union(result, definition['domain'])))
        result.add((subject, RDFS.range, union(result, definition['range'])))
    result.add((CPI.HAS_EXCEPTION, OWL.inverseOf, CPI.EXCEPTION_TO))
    for name in ('Assertion', 'SemanticInstance'):
        result.add((CPI[name], RDF.type, OWL.Class))
    for key in ('sourceRef',):
        result.add((CPI[key], RDF.type, OWL.ObjectProperty))
        result.add((CPI[key], RDFS.range, CPI.SourcePassage))
    for key, dtype in [('status', XSD.string), ('synthetic', XSD.boolean), ('mode', XSD.string), ('ontologyVersion', XSD.string)]:
        result.add((CPI[key], RDF.type, OWL.DatatypeProperty))
        result.add((CPI[key], RDFS.range, dtype))
    return result


def instance_graph(data):
    result = graph()
    envelope = URIRef('urn:cpi:semantic-instance:envelope')
    result.add((envelope, RDF.type, CPI.SemanticInstance))
    result.add((envelope, CPI.mode, Literal(data['mode'])))
    result.add((envelope, CPI.ontologyVersion, Literal(data['ontology_version'])))
    for node in data['nodes']:
        subject = URIRef(node['id'])
        for parent in class_lineage(node['type']):
            result.add((subject, RDF.type, CPI[parent]))
        result.add((subject, RDFS.label, Literal(node['label'])))
        result.add((subject, CPI.status, Literal(node['status'])))
        result.add((subject, CPI.synthetic, Literal(node['synthetic'], datatype=XSD.boolean)))
        for source in node['source_refs']:
            result.add((subject, CPI.sourceRef, URIRef(source)))
        props, _ = class_properties(node['type'])
        for key, value in node['properties'].items():
            spec = props[key]
            if isinstance(value, list):
                if key == 'value':
                    result.add((subject, CPI[key], rdf_list(result, [literal(v, {'type': 'string'}) for v in value])))
                else:
                    for v in value:
                        result.add((subject, CPI[key], literal(v, spec.get('items'))))
            else:
                result.add((subject, CPI[key], literal(value, spec)))
    for edge in data['relationships']:
        subject, predicate, target = URIRef(edge['subject']), CPI[edge['predicate']], URIRef(edge['object'])
        result.add((subject, predicate, target))
        assertion = URIRef(edge['id'])
        result.add((assertion, RDF.type, CPI.Assertion))
        result.add((assertion, RDF.type, RDF.Statement))
        for key, value in [(RDF.subject, subject), (RDF.predicate, predicate), (RDF.object, target)]:
            result.add((assertion, key, value))
        result.add((assertion, CPI.status, Literal(edge['status'])))
        for source in edge['source_refs']:
            result.add((assertion, CPI.sourceRef, URIRef(source)))
    return result


def shapes_graph():
    from .semantic_model import STATUSES
    result = graph()

    def shape(name):
        subject = CPI[name + 'Shape']
        result.add((subject, RDF.type, SH.NodeShape))
        result.add((subject, SH.targetClass, CPI[name]))
        result.add((subject, SH.nodeKind, SH.IRI))
        result.add((subject, SH.closed, Literal(True)))
        result.add((subject, SH.ignoredProperties, rdf_list(result, [RDF.type])))
        return subject

    def property_(subject, path, minimum=0, maximum=None, dtype=None, classes=None):
        p = BNode()
        result.add((subject, SH.property, p))
        result.add((p, SH.path, path))
        result.add((p, SH.minCount, Literal(minimum)))
        if maximum is not None:
            result.add((p, SH.maxCount, Literal(maximum)))
        if dtype:
            result.add((p, SH.datatype, dtype))
        if classes:
            result.add((p, SH.nodeKind, SH.IRI))
            if len(classes) == 1:
                result.add((p, SH['class'], CPI[classes[0]]))
            else:
                options = []
                for c in classes:
                    option = BNode()
                    result.add((option, SH['class'], CPI[c]))
                    options.append(option)
                result.add((p, SH['or'], rdf_list(result, options)))
        return p

    def constraint(subject, code, query):
        node = BNode()
        result.add((subject, SH.sparql, node))
        result.add((node, SH.message, Literal(code)))
        result.add((node, SH.select, Literal(PREFIXES + query)))

    for name in CLASSES:
        subject = shape(name)
        property_(subject, RDFS.label, 1, 1, XSD.string)
        status = property_(subject, CPI.status, 1, 1, XSD.string)
        result.add((status, SH['in'], rdf_list(result, [Literal(s) for s in STATUSES])))
        property_(subject, CPI.synthetic, 1, 1, XSD.boolean)
        property_(subject, CPI.sourceRef, 0 if name == 'SourcePassage' else 1, classes=['SourcePassage'])
        props, required = class_properties(name)
        for key, spec in props.items():
            array = spec.get('type') == 'array'
            p = property_(subject, CPI[key], (spec.get('minItems', 0) if array else 1) if key in required else 0,
                None if array else 1, datatype(spec.get('items', spec)))
            for skey, shkey in [('minLength', SH.minLength), ('minimum', SH.minInclusive), ('pattern', SH.pattern)]:
                if skey in spec:
                    result.add((p, shkey, Literal(spec[skey])))
            if spec.get('format') == 'date':
                result.add((p, SH.pattern, Literal(r'^\d{4}-\d{2}-\d{2}$')))
            if 'enum' in spec:
                result.add((p, SH['in'], rdf_list(result, [literal(v, spec) for v in spec['enum']])))
            if key == 'value':
                options = []
                for dtype in (XSD.string, XSD.decimal, XSD.boolean):
                    option = BNode()
                    result.add((option, SH.datatype, dtype))
                    options.append(option)
                option = BNode()
                result.add((option, SH.node, CPI.ConditionValueListShape))
                options.append(option)
                result.add((p, SH['or'], rdf_list(result, options)))
        for key, relation in RELATIONSHIPS.items():
            if set(class_lineage(name)) & set(relation['domain']):
                property_(subject, CPI[key], relation['min_per_subject'], relation['max_per_subject'], classes=relation['range'])
            elif any(name in class_lineage(domain) for domain in relation['domain']):
                # Superclass shapes also target subclass instances. Permit their
                # additional relationships here; typed edge shapes below enforce
                # that only the declared subclass may actually use those edges.
                property_(subject, CPI[key], classes=relation['range'])
        constraint(subject, 'EXAMPLE_ISOLATION', '''SELECT $this WHERE {
            ?instance a cpi:SemanticInstance; cpi:mode "EXAMPLE" . $this cpi:synthetic false . }''')
        constraint(subject, 'SYNTHETIC_PROVENANCE', '''SELECT $this WHERE {
            $this cpi:synthetic false; cpi:sourceRef ?p . ?p cpi:synthetic true . }''')

    # IN/NOT_IN values are RDF lists; other comparisons use scalar literals.
    values = CPI.ConditionValueListShape
    result.add((values, RDF.type, SH.NodeShape))
    result.add((values, SH.nodeKind, SH.BlankNode))
    path = BNode()
    rest = BNode()
    result.add((rest, SH.zeroOrMorePath, RDF.rest))
    Collection(result, path, [rest, RDF.first])
    property_(values, path, 1, dtype=XSD.string)
    constraint(values, 'CONDITIONS: finite RDF value list', '''SELECT $this WHERE {
        FILTER NOT EXISTS { $this rdf:rest* rdf:nil } }''')

    subject = shape('Assertion')
    for key in (RDF.subject, RDF.predicate, RDF.object):
        p = property_(subject, key, 1, 1)
        result.add((p, SH.nodeKind, SH.IRI))
        if key == RDF.predicate:
            result.add((p, SH['in'], rdf_list(result, [CPI[k] for k in RELATIONSHIPS])))
    p = property_(subject, CPI.status, 1, 1, XSD.string)
    result.add((p, SH['in'], rdf_list(result, [Literal(s) for s in STATUSES])))
    property_(subject, CPI.sourceRef, 1, classes=['SourcePassage'])
    constraint(subject, 'ASSERTION_TRIPLE: reification must identify an asserted triple', '''SELECT $this WHERE {
        $this rdf:subject ?s; rdf:predicate ?p; rdf:object ?o . FILTER NOT EXISTS { ?s ?p ?o } }''')
    constraint(subject, 'DUPLICATE_RELATIONSHIP', '''SELECT $this WHERE {
        $this rdf:subject ?s; rdf:predicate ?p; rdf:object ?o .
        ?other a cpi:Assertion; rdf:subject ?s; rdf:predicate ?p; rdf:object ?o . FILTER (?other != $this) }''')

    subject = shape('SemanticInstance')
    result.add((subject, SH.targetNode, URIRef('urn:cpi:semantic-instance:envelope')))
    result.add((subject, SH['class'], CPI.SemanticInstance))
    p = property_(subject, CPI.mode, 1, 1, XSD.string)
    result.add((p, SH['in'], rdf_list(result, [Literal('EXAMPLE'), Literal('SOURCE_BACKED')])))
    p = property_(subject, CPI.ontologyVersion, 1, 1, XSD.string)
    result.add((p, SH.hasValue, Literal(VERSION)))

    cross = {
        'SourcePassage': [
            ('SOURCE_VERSION', '''SELECT $this WHERE { $this cpi:SOURCE_IN_VERSION ?v; cpi:version ?sv; cpi:source_checksum ?sc .
                ?v cpi:version ?vv; cpi:source_checksum ?vc . FILTER (?sv != ?vv || ?sc != ?vc) }'''),
            ('EXAMPLE_ISOLATION', '''SELECT $this WHERE { ?i a cpi:SemanticInstance; cpi:mode ?mode . $this cpi:origin ?origin .
                FILTER ((STR(?mode) = "EXAMPLE" && STR(?origin) != "ILLUSTRATIVE_EXAMPLE") || (STR(?mode) = "SOURCE_BACKED" && STR(?origin) != "POLICY_SOURCE")) }'''),
        ],
        'PolicyRule': [
            ('SOURCE_VERSION', '''SELECT $this WHERE { $this cpi:PART_OF_VERSION ?v; cpi:DERIVED_FROM ?p .
                ?p cpi:SOURCE_IN_VERSION ?other . FILTER (?v != ?other) }'''),
            ('QUANTITATIVE_RULE', '''SELECT $this WHERE { $this cpi:rule_kind "QUANTITATIVE"^^xsd:string .
                FILTER (NOT EXISTS { $this cpi:HAS_THRESHOLD ?t } || NOT EXISTS { $this cpi:USES_METRIC ?m }) }'''),
            ('THRESHOLD_METRIC', '''SELECT $this WHERE { $this cpi:HAS_THRESHOLD ?t . ?t cpi:MEASURED_BY ?m .
                FILTER NOT EXISTS { $this cpi:USES_METRIC ?m } }'''),
            ('EXCEPTION_LINKS', '''SELECT $this WHERE { $this cpi:HAS_EXCEPTION ?e . FILTER NOT EXISTS { ?e cpi:EXCEPTION_TO $this } }'''),
        ],
        'Threshold': [('THRESHOLD_METRIC: incompatible unit', '''SELECT $this WHERE { $this cpi:MEASURED_BY ?m; cpi:unit ?u .
            FILTER NOT EXISTS { ?m cpi:allowed_units ?u } }''')],
        'Exception': [
            ('EXCEPTION_LINKS', '''SELECT $this WHERE { $this cpi:EXCEPTION_TO ?base . FILTER NOT EXISTS { ?base cpi:HAS_EXCEPTION $this } }'''),
            ('EXCEPTION_LINKS: alternative kind', '''SELECT $this WHERE { $this cpi:IMPLEMENTED_BY_RULE ?r .
                FILTER NOT EXISTS { ?r cpi:rule_kind "EXCEPTION_RULE"^^xsd:string } }'''),
            ('EXCEPTION_LINKS: alternative version', '''SELECT $this WHERE { $this cpi:EXCEPTION_TO ?base; cpi:IMPLEMENTED_BY_RULE ?r .
                ?base cpi:PART_OF_VERSION ?v1 . ?r cpi:PART_OF_VERSION ?v2 . FILTER (?v1 != ?v2) }'''),
        ],
        'ConditionGroup': [
            ('CONDITION_LOGIC: cycle', '''SELECT $this WHERE { $this cpi:HAS_MEMBER+ $this }'''),
            ('CONDITION_LOGIC: NOT cardinality', '''SELECT $this WHERE { $this cpi:logic "NOT"^^xsd:string; cpi:HAS_MEMBER ?a, ?b . FILTER (?a != ?b) }'''),
        ],
        'Condition': [
            ('CONDITIONS: EXISTS omits value', '''SELECT $this WHERE { $this cpi:operator "EXISTS"^^xsd:string; cpi:value ?v }'''),
            ('CONDITIONS: missing value', '''SELECT $this WHERE { $this cpi:operator ?op . FILTER (STR(?op) != "EXISTS") FILTER NOT EXISTS { $this cpi:value ?v } }'''),
            ('CONDITIONS: membership uses a list', '''SELECT $this WHERE { $this cpi:operator ?op; cpi:value ?v .
                FILTER (STR(?op) IN ("IN", "NOT_IN")) FILTER NOT EXISTS { ?v rdf:first ?item } }'''),
            ('CONDITIONS: scalar comparison', '''SELECT $this WHERE { $this cpi:operator ?op; cpi:value ?v .
                FILTER (STR(?op) NOT IN ("IN", "NOT_IN", "EXISTS")) FILTER (!isLiteral(?v)) }'''),
            ('CONDITIONS: numeric ordered comparison', '''SELECT $this WHERE { $this cpi:operator ?op; cpi:value ?v .
                FILTER (STR(?op) IN ("GT", "GTE", "LT", "LTE")) FILTER (datatype(?v) != xsd:decimal) }'''),
        ],
        'EffectivePeriod': [('EFFECTIVE_DATES', '''SELECT $this WHERE { $this cpi:start_date ?s; cpi:end_date ?e . FILTER (?e < ?s) }''')],
        'PolicySection': [
            ('CONTAINMENT: section cycle', '''SELECT $this WHERE { $this cpi:PARENT_SECTION+ $this }'''),
            ('CONTAINMENT: parent version', '''SELECT $this WHERE { $this cpi:PARENT_SECTION ?p; cpi:PART_OF_VERSION ?v .
                ?p cpi:PART_OF_VERSION ?other . FILTER (?v != ?other) }'''),
            ('CONTAINMENT: rule version', '''SELECT $this WHERE { $this cpi:PART_OF_VERSION ?v; cpi:CONTAINS_RULE ?r .
                ?r cpi:PART_OF_VERSION ?other . FILTER (?v != ?other) }'''),
        ],
        'PolicyVersion': [('CONTAINMENT: version children', '''SELECT $this WHERE {
            { $this cpi:CONTAINS_RULE ?child } UNION { $this cpi:CONTAINS_SECTION ?child }
            ?child cpi:PART_OF_VERSION ?other . FILTER ($this != ?other) }''')],
    }
    for kind, constraints in cross.items():
        for code, query in constraints:
            constraint(CPI[kind + 'Shape'], code, query)
    # Validate domain/range even when a malformed RDF node has no business type.
    for key, relation in RELATIONSHIPS.items():
        typed = CPI[key + 'EdgeShape']
        result.add((typed, RDF.type, SH.NodeShape))
        result.add((typed, SH.targetSubjectsOf, CPI[key]))
        options = []
        for domain in relation['domain']:
            option = BNode()
            result.add((option, SH['class'], CPI[domain]))
            options.append(option)
        result.add((typed, SH['or'], rdf_list(result, options)))
        property_(typed, CPI[key], classes=relation['range'])
    # All application direct edges must have evidence-bearing reification.
    all_edges = CPI.AssertionCoverageShape
    result.add((all_edges, RDF.type, SH.NodeShape))
    for relation in RELATIONSHIPS:
        result.add((all_edges, SH.targetSubjectsOf, CPI[relation]))
    alternatives = ', '.join('cpi:' + k for k in RELATIONSHIPS)
    constraint(all_edges, 'SOURCE_REFERENCES: direct edge requires assertion evidence', f'''SELECT $this WHERE {{
        $this ?p ?o . FILTER (?p IN ({alternatives}))
        FILTER NOT EXISTS {{ ?a a cpi:Assertion; rdf:subject $this; rdf:predicate ?p; rdf:object ?o; cpi:sourceRef ?source }} }}''')
    return result
