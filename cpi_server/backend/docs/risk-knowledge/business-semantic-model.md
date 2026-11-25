# Credit policy business semantic schema

Version 1.4.0 is defined in `app/risk_knowledge/semantic_model.py`. The schema is
curated in code, grounded in the existing policy taxonomy, the Credit Dossier
deal schema, CPI's canonical credit-data registry and the risk data dictionary.
The source model and field anchors are listed in the semantic contract.
`semantic_extraction.py` builds the populated policy graph from the current
extraction records and reviewed scopes. The checked-in snapshot contains
35 policy documents. Its published scopes cover products, subsectors, industry
tiers, segments, and geographies. CRE product and property subsector evidence is
distinct from borrower industry evidence.

| Layer | Example paths |
|---|---|
| Domain | Borrower operates in Industry, is incorporated in Country, is domiciled in Country, and belongs to CorporateGroup. CreditRequest is requested by Borrower and requests Facility. Facility has Product, Tenor, and Collateral, and is booked in a Jurisdiction. |
| Policy | CreditPolicy has PolicyVersion. PolicyVersion contains PolicySection, which contains PolicyRule. Each rule derives from an exact source passage and can carry conditions, thresholds, taxonomy classifications, exceptions, and approval requirements. |
| Applicability | PolicyVersion and PolicyRule link to scoped products, industries, borrower types, and geographies where documented. Condition links to typed scope values and registered attributes. PolicyRule evaluates RiskAttribute, and known risk metrics bind to canonical deal fields. |
| Decision | CreditRequest has RuleAssessment. RuleAssessment assesses the exact PolicyRule and has a DecisionOutcome, such as pass, breach, exception, or referral. |

## Acceptance questions

Open **Policy Intelligence → Risk Knowledge → Knowledge graph → Policy questions**.
Borrower applicability uses the selected credit request's authorized facts.
Product, industry, and geography searches show explicit scope paths with citations.
For product scope inherited from a policy version, the result identifies that
inheritance. Additional conditions may still affect applicability.

| Question | Evidence and graph path |
|---|---|
| Which policies apply to a borrower? | Match reviewed policy scope and published rule conditions to the request. Missing facts or unresolved scope produce **Unable to Determine**. |
| Which policies cover an industry or jurisdiction? | Find exact positive scope edges. Industries, subsectors, industry tiers, named geographies, and home/foreign jurisdiction remain distinct. |
| Which rules cover a product or depend on rating? | Follow rule scope, inherited product scope, and cited rating dependencies. Explicit letter-rating comparisons use the declared rating scale. |
| What exposure limits, collateral requirements, approvals, and exceptions are documented? | Follow the rule subjects, threshold and approval links, and exception paths. Approval triggered by a policy breach and approval above a delegated authority threshold use separate edges. |
| Which policy class created the rule? | Explicit derivation requires a source statement. The query also shows taxonomy classifications. |
| Which rule version was effective on a date? | Select the policy edition by effective date. Archived semantic rules remain available after supersession. A rule-specific period takes precedence for that rule. A unique explicit source rule code or identical rule wording can resolve a reference across editions. |

Use **Browse a relationship type** to explore any declared predicate without a
prewritten question. **Ontology or source gaps** shows published coverage and
unbound fields with exact source examples for review.

## Upload and rebuild

In **Source Assets**, upload a PDF, DOCX, or UTF-8 text policy. Choose an existing
policy for a revision, enter its version and effective date, then select
**Upload and compare**. The comparison shows added, removed, and unchanged
passages against the preceding source. The upload is staged for the signed-in
user. **Revisit ontology and rebuild graph** registers the version and queues
semantic extraction. During extraction the replacing version may have no
published graph rules. The worker archives the prior extraction, validates the
rebuilt graph, stores a shared snapshot, and reports reviewed rule changes and
ontology candidates. Unresolved rule or scope proposals remain available for
review. Adding an ontology predicate requires an explicit model change.

**Rebuild from reviewed sources** reprojects the current corpus using the
installed ontology and stores a validated snapshot without a new extraction run.

The matcher evaluates the original condition tree, including nested groups and
exclusions. Direct scope links help navigation. A taxonomy classification links
a rule to its policy category or topic. Explicit derivation from a policy class
has its own predicate.

The request graph adds known facts for the selected deal through the authenticated
`/api/risk-knowledge/requests/{request_id}/graph` route. Generic deal geography
produces a reported geography relationship. Incorporation, domicile, country of
risk, and booking jurisdiction each require an explicit source field. The
compliance assessment response includes a `request_graph` extension whose rule
IDs and policy evidence resolve against the assessment's identified knowledge
snapshot. Consumers can join by node ID and union source references for shared
terms. Manual-review outcomes appear as referrals. Exception outcomes are
available in the model for recorded decisions. An exception clause or approval
requirement alone cannot establish an exception decision.

`app/risk_knowledge/semantic_rdf.py` generates the OWL/RDFS ontology, SHACL Core
and SHACL-SPARQL constraints, and RDF representation of JSON instances. It does
not read customer records or create a production knowledge graph.

Generate the portable, validated package from `backend`:

```powershell
.venv/Scripts/python.exe scripts/export_semantic_model.py
```

The files are written to `dm_server/seed_others/outputs/ontology/`. The package
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
under `dm_server/seed_others/outputs/extracted-knowledge`. Schema validation and business review
remain separate operations. Schema validity does not grant business approval,
prove correct interpretation of a source, or make an assertion executable.
To regenerate the connected graph from the saved policy snapshot, run
`.venv/Scripts/python.exe scripts/export_connected_knowledge.py --records ../../dm_server/seed_others/outputs/extracted-knowledge/policy-rule-knowledge.json`
from the backend directory.

`.venv/Scripts/python.exe scripts/verify_policy_competency.py --store` verifies
archived file checksums and extracted passages against the shared catalog,
executes sample competency questions, and stores the validated graph.

Standards: [JSON Schema](https://json-schema.org/draft/2020-12/json-schema-core),
[OWL 2](https://www.w3.org/TR/owl2-primer/),
[SHACL](https://www.w3.org/TR/shacl/).
