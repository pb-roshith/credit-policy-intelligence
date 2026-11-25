"""Generate and validate portable credit-policy business ontology artifacts.

From backend: .venv/Scripts/python.exe scripts/export_semantic_model.py
Validate another JSON instance: append --validate <instance.json>.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import SEED_OUTPUTS_DIR
from app.risk_knowledge.semantic_model import (VERSION, NAMESPACE, CLASSES, RELATIONSHIPS,
    RULES, semantic_contract, instance_schema, example_instance, validate_instance)
from app.risk_knowledge.semantic_rdf import ontology_graph, shapes_graph, instance_graph


def readme():
    lines = ['# Credit policy business semantic model', '',
        f'Version **{VERSION}**. Design status **CURRENT**. Namespace `{NAMESPACE}`.', '',
        'This package defines the business ontology for credit policy knowledge. '
        'The source-backed policy graph is available in the connected knowledge package. '
        'The supplied example is fictional and cannot establish a policy requirement or approval.', '',
        '## Machine-readable deliverables', '',
        '| File | Purpose |', '|---|---|',
        '| [semantic-model.json](semantic-model.json) | Class/property dictionary, typed relationships, cardinalities and constraint catalogue |',
        '| [instances.schema.json](instances.schema.json) | JSON Schema 2020-12 for JSON instances |',
        '| [ontology.ttl](ontology.ttl) | OWL/RDFS classes, inheritance, object/data properties and domain/range semantics |',
        '| [shapes.ttl](shapes.ttl) | SHACL Core and SHACL-SPARQL validation constraints |',
        '| [example.json](example.json) | Explicitly illustrative JSON instance, including 80% LTV and exception approval |',
        '| [example.ttl](example.ttl) | The same illustrative instance as RDF, with evidence-bearing assertion reification |',
        '| [validation-report.json](validation-report.json) | Actual schema, Turtle and SHACL validation results |',
        '| [manifest.json](manifest.json) | SHA-256 checksums and package version |', '',
        '## Reading the model', '',
        *[f"- **{layer['name']}**. {layer['description']}" for layer in semantic_contract()['layers']], '',
        '```mermaid', 'flowchart LR',
        '  CreditRequest -->|REQUESTED_BY| Borrower', '  Borrower -->|OPERATES_IN_INDUSTRY| Industry',
        '  Borrower -->|INCORPORATED_IN| Country', '  CreditRequest -->|REQUESTS_FACILITY| Facility',
        '  Facility -->|HAS_PRODUCT| Product', '  CreditPolicy -->|HAS_VERSION| PolicyVersion',
        '  PolicyVersion -->|CONTAINS_SECTION| PolicySection',
        '  PolicySection -->|CONTAINS_RULE| PolicyRule', '  PolicyVersion -->|APPLIES_TO_PRODUCT| Product',
        '  CreditRequest -->|HAS_RULE_ASSESSMENT| RuleAssessment', '  RuleAssessment -->|ASSESSES_RULE| PolicyRule',
        '  RuleAssessment -->|HAS_OUTCOME| DecisionOutcome',
        '  PolicyRule -->|USES_METRIC| RiskMetric', '  PolicyRule -->|HAS_THRESHOLD| Threshold',
        '  Threshold -->|MEASURED_BY| RiskMetric', '  PolicyRule -->|HAS_EXCEPTION| Exception',
        '  Exception -->|REQUIRES_APPROVAL| ApprovalRequirement',
        '  ApprovalRequirement -->|REQUIRES_APPROVAL_FROM| ApprovalAuthority', '```', '',
        'A threshold stores operator, numeric value and unit. For example, `LTE`, `80`, `%` is '
        'at most 80 percent, not equality and not a value of 0.8. The metric declares permitted units. '
        'Credit score scales and SME size definitions are not assumed. A policy identity has separately '
        'identified versions; rules and exact passages belong to the same version.', '',
        'Conditions use explicit AND/OR/NOT groups. An exception links to its base rule and may link to '
        'an alternative exception rule and an approval requirement. An authority requirement is distinct '
        'from an approval decision. Evidence requirements are distinct from actual evidence artifacts.', '',
        '## Classes', '', '| Class | Parent | Definition | Required data properties |', '|---|---|---|---|']
    for name, spec in CLASSES.items():
        lines.append(f"| {name} | {spec['parent'] or '—'} | {spec['definition']} | {', '.join(spec['required_properties']) or '—'} |")
    lines.extend(['', 'Every entity also carries an IRI, label, status, synthetic flag and source references. '
        'SourcePassage and OperationalEvidence can be referenced directly as evidence.', '',
        '## Typed relationships', '', '| Relationship | Domain | Range | Per-subject count | Meaning |', '|---|---|---|---|---|'])
    for name, spec in RELATIONSHIPS.items():
        lines.append(f"| {name} | {' or '.join(spec['domain'])} | {' or '.join(spec['range'])} | {spec['min_per_subject']}..{spec['max_per_subject'] if spec['max_per_subject'] is not None else '*'} | {spec['definition']} |")
    lines.extend(['', 'Counts apply to each subject of the declared domain. Missing optional scope or validity '
        'does not establish unrestricted scope or current validity.', '', '## Validation', '',
        'JSON Schema checks local structure. The Python/API semantic validator additionally checks IDs, '
        'endpoint references/types, relationship counts, units, provenance, source versions, condition logic '
        'and dates. Use both when consuming JSON; JSON Schema alone cannot resolve arbitrary cross-node IDs.', '',
        'RDF uses direct business triples plus `cpi:Assertion` / `rdf:Statement` records for per-edge status '
        'and source references. Literal arrays other than Condition.value are represented as repeated '
        'properties. IN/NOT_IN values use RDF lists. Subclass types are materialized in example RDF.', '',
        'Validate RDF against shapes.ttl with inference **none** and SHACL-SPARQL support. OWL is '
        'a semantic declaration, not closed-world validation. Avoid inference before validation: inferred '
        'inverse relationships would lack the required evidence-bearing assertions. JSON transport '
        'uniqueness and JSON array structure are additionally enforced by the JSON validator.', '',
        '```powershell', '# From cpi_server/backend',
        '.venv/Scripts/python.exe scripts/export_semantic_model.py',
        '.venv/Scripts/python.exe scripts/export_semantic_model.py --validate ../../dm_server/backend/seed_others/outputs/ontology/example.json',
        '```', '', '```python', 'from rdflib import Graph', 'from pyshacl import validate',
        'conforms, report, text = validate(',
        '    Graph().parse("example.ttl", format="turtle"),',
        '    shacl_graph=Graph().parse("shapes.ttl", format="turtle"),',
        '    inference="none", advanced=True, meta_shacl=True,', ')', '```', '',
        '### Semantic constraints', '', *[f'- **{code}**: {text}' for code, text in RULES], '',
        '## Integration and governance', '',
        '- The authenticated API exposes `/api/risk-knowledge/semantic-model`, `/schema`, '
        '`/ontology.ttl`, `/shapes.ttl`, `/example`, and POST `/validate` under that prefix.',
        '- `CLASSIFIED_AS` references the taxonomy concept ID and version; classification never establishes rule applicability.',
        '- `BINDS_TO_ATTRIBUTE` is an explicit binding assertion. Similar attribute names are not equivalent by default.',
        '- The executable policy compiler reads its vocabulary from `app/risk_knowledge/policy_ontology.py`. The API route `/policy-ontology` returns this business semantic contract.',
        '- Existing stored ontology relationship labels are not automatically converted, approved or declared equivalent to this contract.',
        '- Validation checks structure and evidence references. Approvals require a recorded decision.',
        '- No existing policy, rule, ontology assertion or taxonomy approval is changed by generating these files.', '',
        '## Standards references', '',
        '- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-core)',
        '- [OWL 2](https://www.w3.org/TR/owl2-primer/)',
        '- [SHACL](https://www.w3.org/TR/shacl/)', ''])
    return '\n'.join(lines)


def export(output):
    from jsonschema import Draft202012Validator
    from rdflib import Graph
    from pyshacl import validate
    output.mkdir(parents=True, exist_ok=True)
    schema, example = instance_schema(), example_instance()
    Draft202012Validator.check_schema(schema)
    local_report = validate_instance(example)
    if not local_report['conforms']:
        raise ValueError(local_report)

    def json_file(name, data):
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

    json_file('semantic-model.json', semantic_contract())
    json_file('instances.schema.json', schema)
    json_file('example.json', example)
    graphs = {'ontology.ttl': ontology_graph(), 'shapes.ttl': shapes_graph(), 'example.ttl': instance_graph(example)}
    for name, rdf in graphs.items():
        rdf.serialize(output / name, format='turtle')
    parsed = {name: Graph().parse(output / name, format='turtle') for name in graphs}
    conforms, report, report_text = validate(parsed['example.ttl'], shacl_graph=parsed['shapes.ttl'],
        inference='none', advanced=True, meta_shacl=True)
    if not conforms:
        raise ValueError(report_text)
    # A malformed unit must be rejected by the portable shapes, not just Python.
    invalid = example_instance()
    next(n for n in invalid['nodes'] if n['id'].endswith(':threshold'))['properties']['unit'] = 'score_points'
    rejected, _, _ = validate(instance_graph(invalid), shacl_graph=parsed['shapes.ttl'], inference='none', advanced=True)
    if rejected:
        raise ValueError('SHACL failed to reject incompatible threshold units')
    validation = {'ontology_version': VERSION, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'json_schema_meta_validation': True, 'json_instance_validation': local_report,
        'turtle_parse_validation': {name: {'valid': True, 'triples': len(rdf)} for name, rdf in parsed.items()},
        'shacl_meta_validation': True, 'shacl_example_conforms': bool(conforms),
        'shacl_rejects_wrong_unit': not bool(rejected), 'design_status': 'CURRENT',
        'example_status': 'ILLUSTRATIVE_ONLY', 'report': report_text}
    json_file('validation-report.json', validation)
    (output / 'README.md').write_text(readme(), encoding='utf-8')
    files = sorted([*graphs, 'semantic-model.json', 'instances.schema.json', 'example.json', 'validation-report.json', 'README.md'])
    json_file('manifest.json', {'ontology_version': VERSION, 'status': 'CURRENT',
        'files': {name: {'sha256': hashlib.sha256((output / name).read_bytes()).hexdigest(), 'bytes': (output / name).stat().st_size} for name in files}})
    archive = output / f'credit-policy-ontology-v{VERSION}.zip'
    with ZipFile(archive, 'w', ZIP_DEFLATED) as package:
        for name in [*files, 'manifest.json']:
            package.write(output / name, name)
    return {'output': str(output.resolve()), 'archive': str(archive.resolve()), 'classes': len(CLASSES),
        'relationship_types': len(RELATIONSHIPS), 'validation': validation}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=SEED_OUTPUTS_DIR / 'ontology')
    parser.add_argument('--validate', type=Path)
    args = parser.parse_args()
    if args.validate:
        data = json.loads(args.validate.read_text(encoding='utf-8'))
        report = validate_instance(data)
        print(json.dumps(report, indent=2))
        sys.exit(0 if report['conforms'] else 1)
    print(json.dumps(export(args.output), indent=2))


if __name__ == '__main__':
    main()
