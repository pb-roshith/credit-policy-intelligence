# Credit policy business semantic schema

`app/risk_knowledge/semantic_model.py` defines the current business ontology used by semantic extraction, the populated policy graph and compliance matching. Version 1.2.0 includes policy-version applicability and exclusion relationships.

The business contract has 24 classes, 35 typed relationship predicates, explicit
property types, per-subject relationship cardinalities and 13 groups of semantic
constraints. It covers customers/borrowers, applications, loans, policy versions,
sections, rules, conditions, thresholds, product/segment/geographic scope,
metrics, exceptions, approvals, evidence, dates, source passages, taxonomy
references and data attributes.

`app/risk_knowledge/semantic_rdf.py` generates the OWL/RDFS ontology, SHACL Core
and SHACL-SPARQL constraints, and RDF representation of JSON instances. It does
not read customer records or create a production knowledge graph.

Generate the portable, validated package from `backend`:

```powershell
.venv/Scripts/python.exe scripts/export_semantic_model.py
```

The files are written to `cpi_server/outputs/ontology/` inside `cpi_server`. The package
includes the semantic contract JSON, JSON Schema 2020-12, ontology Turtle,
SHACL Turtle, illustrative JSON/RDF instances, a full dictionary/guide,
validation results and checksum manifest, bundled in a ZIP archive.

The example is explicitly synthetic. Its 80% LTV ceiling, 85% exception ceiling,
SME product scope and credit manager requirement are illustrative values, not
requirements extracted from the current policy corpus. DTI and credit score
definitions carry no invented thresholds or universal score scale.

Authenticated API routes:

- `GET /api/risk-knowledge/semantic-model`: full semantic contract.
- `GET /api/risk-knowledge/semantic-model/schema`: JSON transport schema.
- `GET /api/risk-knowledge/semantic-model/ontology.ttl`: OWL/RDFS definitions.
- `GET /api/risk-knowledge/semantic-model/shapes.ttl`: RDF validation shapes.
- `GET /api/risk-knowledge/semantic-model/example`: illustrative instance.
- `POST /api/risk-knowledge/semantic-model/validate`: consistency report for
  a JSON instance. A response with `conforms=false` is a failed validation.

These routes perform no database writes or approvals. The Ontology tab opens
the semantic schema with downloads, class/property definitions,
relationships and constraints. The populated graph is available in Knowledge graph;
Policy Evidence displays the current source passages.

Consumers must run both JSON Schema and the supplied semantic validator for
JSON instances. JSON Schema checks local types; the semantic validator checks
cross-node references, endpoint types, cardinalities, metric/unit compatibility,
source versions, provenance, condition logic, containment, effective dates and
example isolation. RDF consumers use SHACL-SPARQL with inference disabled as
explained in the generated guide. OWL declarations alone are not validation.

Source-backed population is provided by `semantic_pipeline.py` and exported separately
under `cpi_server/outputs/extracted-knowledge`. Schema validation and business review
remain separate operations. Schema validity does not grant business approval,
prove correct interpretation of a source, or make an assertion executable.

Standards: [JSON Schema](https://json-schema.org/draft/2020-12/json-schema-core),
[OWL 2](https://www.w3.org/TR/owl2-primer/),
[SHACL](https://www.w3.org/TR/shacl/).
