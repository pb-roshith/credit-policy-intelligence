# Extracted policy rules and knowledge graph

These files contain actual AI extraction results from the registered policy corpus. Synthetic source labels are retained.

[Review workbook](extracted-policy-rules.xlsx) · [Machine-readable graph](knowledge-graph.json) · [RDF graph](knowledge-graph.ttl) · [Validation](knowledge-validation.json)

- policies: 35
- source_passages: 1609
- extracted_rules: 1078
- published_rules: 863
- proposed_rules: 215
- approved_policy_scopes: 19
- policy_scopes_needing_review: 16
- unresolved_passages: 159
- failed_batches: 0
- batches_using_existing_graph: 79
- resolved_exception_nodes: 1
- nodes: 3622
- relationships: 7246
- ontology_version: 1.2.0

Validated rules receive auditable automatic initial approval. Proposed rules, ambiguous references and failed batches remain visible in the review queue. Human corrections/rejections are versioned in the audit history and survive extraction retries.

The graph supplies bounded, source-backed context to subsequent AI batches. Context IDs and fingerprints are recorded in the workbook. Context cannot invent a threshold or policy scope.

In the application use Policy Rule Library for review and Knowledge graph for progressive exploration. Clicking a node opens its connected neighborhood, with six neighbors drawn at a time and a searchable directory for all policies and rules.

Policy versions can carry source-backed HAS_APPLICABILITY and HAS_EXCLUSION condition groups. Compliance Review inherits this scope before checking individual rule conditions. Proposed scopes remain unresolved and can be reviewed in Policy Evidence.

Only current source-backed corpus artifacts are included in the release package.
