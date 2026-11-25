# Graph-informed AI policy extraction

The default selected/all-policy extraction workflow is now
`policy-semantic-llm-v1`. It uses the configured AI provider (Gemini or Mistral),
the policy taxonomy and the business semantic ontology. The earlier grammar
compiler is retained as an explicit legacy implementation; it is no longer the
default selected-policy extraction path.

For each current source policy, in sequence:

1. Ingest the registered source with existing version/checksum tracking.
2. Supply bounded primary clauses, explicitly identified scope/definition
   context, controlled vocabulary, business ontology and relevant approved
   rules retrieved from the existing graph.
3. Ask the LLM for atomic quantitative/qualitative requirements and an explicit
   RULES/NON_RULE/UNRESOLVED disposition for every primary clause.
4. Validate source identity, exact quotes, numbers, amount scales, units,
   logical groups, source versions, typed relationships and exception targets.
   PDF whitespace can be restored to the original exact source span. Evidence
   elsewhere in the same explicitly cited clause is retained as a supporting
   quotation. No missing business fact is manufactured.
5. Persist validated rules with auditable automatic initial approval. Keep
   unsupported or ambiguous interpretations proposed. Update the semantic graph
   before extracting the next batch/policy.

Synthetic-labelled policies still have normative policy bodies. Dedicated
training prompts/scenarios are excluded from normative extraction, while
synthetic source flags are retained. A zero-rule response for source text with
normative language is flagged for review rather than silently declared complete.

The source record, context rule IDs, ontology/taxonomy fingerprints, coverage,
failed batches and review history are durable JSONB metadata in the existing
PostgreSQL policy store. Conditional writes protect reviewer changes. Source
version locks prevent stale publications. Retries reuse successful source
checkpoints; unresolved batches can be retried. Human overrides are preserved.

Policy identities/versions/sections contain rules. Rules connect to products,
segments, geography, metrics, thresholds, conditions, evidence requirements,
approval requirements and taxonomy concepts. Exceptions connect to explicitly
resolved base rules. Relative references such as “above” need a unique supported
antecedent. Ambiguous or dangling references do not become confirmed graph edges.
Rejecting a base rule removes its dependent exceptions from active graph context.

Ontology 1.1.0 adds an optional `Condition.unit`, allowing `loan_amount GT 50
lakh` without losing the amount scale or inventing a currency. Canonical entities
use curated taxonomy aliases; similarly named unknown concepts are not merged.

The application exposes:

- **Policy Rule Library**: source-backed AI rules, conditions, thresholds,
  provenance and approved/proposed/rejected state. Analysts/admins can edit,
  approve an override, reject or return a rule for correction, with a rationale.
- **Knowledge graph**: six policy nodes initially; six neighbors per expansion;
  a 30-node visual window, focus and back controls. Evidence and classification
  nodes are lower-priority neighbors to avoid overwhelming the business view.
- **Coverage and issues**: unresolved passages and failed batches, with retry.
- **Operational rule versions / request trace**: the existing executable rule
  workflow remains available separately. Automatic knowledge approval does not
  silently activate or replace operational credit-decision rules.

Authenticated routes:

- `GET /api/risk-knowledge/semantic-knowledge`
- `GET /api/risk-knowledge/semantic-graph?focus=<IRI>&offset=0&limit=6`
- `GET /api/risk-knowledge/semantic-knowledge/export`
- `POST /api/risk-knowledge/semantic-rules/review` (analyst/admin)
- Existing `POST /api/risk-knowledge/extractions` and retry endpoints use this
  pipeline and the existing durable inventory job worker.

Run/export from `backend`:

```powershell
.venv/Scripts/python.exe scripts/run_semantic_extraction.py
.venv/Scripts/python.exe scripts/run_semantic_extraction.py --resume <job-id>
.venv/Scripts/python.exe scripts/revalidate_semantic_knowledge.py
.venv/Scripts/python.exe scripts/export_connected_knowledge.py
```

Revalidation performs no LLM calls. It checks already extracted assertions
against their exact stored sources, preserves human decisions, and records
resulting automatic approvals in the audit history. Review artifacts and JSON/RDF
graph snapshots are written to `dm_server/seed_others/outputs/extracted-knowledge/`.

The live user-sentence demonstration runs in an isolated temporary SQLite store
and writes `user-ltv-example.json`. It is explicitly illustrative and never
populates the shared corpus graph.

Policy Evidence (formerly Policy Representation) reads `GET /api/risk-knowledge/semantic-policies/{policy_id}/representation`.
It joins current SQL source passages to the same current semantic records used
by the Policy Rule Library. Reading this view performs no extraction or writes
and does not require a legacy grammar representation. Passages without a current
extraction remain visible as unprocessed. Primary citations, supporting citations,
proposed rules and quotation validation warnings are retained separately. Historical
rule versions are excluded. Graph navigation shows a focus and up to six neighbors;
review links open the selected policy in the current rule library.

Open Policy Evidence from the Risk Knowledge navigation, a policy?s evidence button,
or a rule?s policy/source link. Rule links select the policy and original source passage.
This is a source-verification view over existing extraction records, not an additional
modeling or extraction stage.

The knowledge graph viewer opens a node's neighborhood on a single click. Its
directory lists all 35 current policies; policy neighborhoods list every published
rule, with six neighbors drawn at a time. Rule neighborhoods prioritize product,
segment, metric, threshold, exception and approval connections. Further clicks
follow threshold-to-metric, exception-to-approval and approval-to-authority links.
Numeric operators and source values appear on the nodes. Unpublished extractions
remain in the rule library and are counted separately.

The graph API projects a policy-to-rule `CONTAINS_RULE` navigation shortcut over
the existing rule/version/policy path. Such edges have `derived=true` and a `via`
version reference. They do not modify stored assertions or the ontology schema.

Compliance Review now uses `semantic_matching.GraphMatcher`, rather than the older
numeric compiler inventory. It traverses current policy/version/section/rule paths,
then checks product, customer segment, geography, AND/OR/NOT conditions and exception
inheritance. Taxonomy synonyms are explicit; no fuzzy or LLM relevance score selects
rules. Monetary magnitudes and compatible units are normalized without foreign exchange
assumptions. Missing/conflicting facts and unresolved scope remain unknown.

Ontology 1.2.0 adds `HAS_APPLICABILITY` and `HAS_EXCLUSION` from PolicyVersion to
ConditionGroup. `scripts/enrich_policy_scopes.py` extracts policy-wide scope with
exact source citations. Source-validated scope receives initial system approval;
ambiguous/configuration-dependent scope remains proposed. Policy Evidence supports
audited reviewer overrides with source and digest validation. Human overrides survive
re-extraction. Individual rules inherit approved policy scope before their narrower
conditions are evaluated. Missing policy scope is never treated as universal.

`semantic_assessment` evaluates only matching published rules. Numeric comparisons
use available request facts; qualitative duties, required approvals and documentary
requirements remain for manual verification. Compliance Review can supplement missing
numeric actuals with explicitly manufactured demonstration observations after matching;
it does not change request facts or infer that an approval requirement was satisfied. Proposed rules and scope,
unresolved passages and missing data keep overall coverage incomplete.

One bounded LLM call explains up to 12 graph-retrieved results with validated rule
citations, without changing selection or outcomes. Provider failure leaves the
deterministic assessment available. The UI lists every matching rule, plus searchable
matched/excluded/unresolved decision traces and links to Policy Evidence.

Account-scoped saved reviews retain semantic URI IDs, rule snapshots, request/knowledge
fingerprints and graph traces as immutable JSON. They are not inserted under numeric
foreign keys belonging to the legacy operational inventory. The latest-review endpoint
invalidates snapshots after knowledge or request facts change; historical reviews remain
readable. Policy mapping and applicability endpoints use the same semantic matcher.

The assessment runner enables `semantic_actuals` generation for missing numeric
actuals and sample qualitative review records. Numeric samples are deterministic per
request/metric/unit family and are shared across rules. Existing observations,
conflicting facts and ambiguous entity selections are not replaced. Every generated
value carries `SYNTHETIC`/`MANUFACTURED` provenance, generator version and source
identifier in the saved assessment. Qualitative sample observations retain manual
review outcomes. No applicability attributes or policy thresholds are manufactured.

Compliance results and Policy Rule Library both offer All / Qualitative /
Quantitative filters. Exception rules with numeric thresholds are quantitative;
exceptions and other duties without thresholds are qualitative. Filters combine
with policy/search filters and reset pagination. Assessment engine v2 invalidates
older saved v1 assessments so users can rerun them with the new actual-data behavior.
