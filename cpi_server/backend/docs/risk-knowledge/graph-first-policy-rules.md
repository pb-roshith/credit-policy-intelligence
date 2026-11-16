# Graph-first policy rules

## Grammar and ontology v2: LTV review

The LTV parser now preserves shared property conditions and separate loan-programme or vehicle-condition branches. A complete investment-property statement with 70% for conventional and 75% for government-insured loans produces two graph requirements and two drafts from one source passage. Secondary/vacation-home alternatives retain their OR grouping inside the AND with loan programme. New/used auto ceilings retain the auto-loan facility restriction. All branches must be accounted for by the coverage validator; deleting or altering one invalidates compilation.

Explicit input bindings are `property_type` -> `collateral.property_type`, `loan_program` -> `facility.loan_program`, and `vehicle_condition` -> `collateral.vehicle_condition`. These values are not inferred from a facility name. Missing facts remain unknown. Unsupported qualifiers, examples, exceptions, mixed overlapping product matrices and ambiguous limits remain unresolved.

Version 2 also classifies isolated numbering and known page furniture as document structure, and bounded purpose/background language as context. All source text and offsets are retained. A purpose-looking sentence containing a limit, obligation, exception or scope exclusion is not cleared as background. The source classification is recorded on each coverage row and rechecked by the compiler; a model's claim that something is background is not sufficient.

The stored LTV Ceilings representation was rebuilt without a model call: 160 source passages now contain three deterministically interpreted passages producing six rule drafts, 29 structure/background/context passages and 128 unresolved passages. The unresolved passages include genuine scope, approval, exception, monitoring and other obligations outside these grammar patterns. This is not complete policy extraction or operational approval. Existing historical representations are retained under their old versioned IDs.

In the representation screen, **Recognised requirements** is the default list; **Needs interpretation** shows gaps, while structure/background can be inspected separately. Each recognised passage shows a readable applies-when / requirement / exceptions table, with structured editing under Advanced. Empty interpretations cannot be approved. A focused source graph excludes the policy root as a traversal bridge, so selecting one passage does not expand back out to all 160 passages.

The operational **Extract Rules** action now follows this order:

1. Ingest the registered source and retain its checksum, version and exact clauses.
2. Match complete source passages against a versioned policy vocabulary and grammar.
3. Persist typed requirement, metric, constraint, scope, exception and source-span nodes and their directed relationships.
4. Compile inventory drafts by traversing this persisted graph.
5. Use an LLM only for passages the deterministic grammar could not interpret. Its output is a source-checked **proposal**, never an executable rule.

`app/risk_knowledge/graph_first.py` is the operational entry point. Both inventory jobs and direct `rule_extraction.process_policy` calls route here. The old LLM-first helper/class remains for historical supplemental code and isolated tests; operational extraction does not invoke its classification, enrichment, ontology-discovery, mapping or extraction passes. Automatic LLM quality review is also removed from extraction jobs. Explicit advisory review tools are separate.

## Vocabulary, ontology and source grammar

`policy_ontology.py` declares allowed metric/input bindings, units, facility values, scope fields, rating ordering and graph relationship types. These are explicit application contracts, not relationships inferred from the old automatically approved ontology collection. A representation includes the ontology contract, its hash and version, and the grammar version. Changing the contract changes the representation identity.

Spreadsheet links require exact source-schema labels and an explicit source-entity binding. An attribute named Tenor in a historical bureau instrument is not automatically equated with the requested tenor of the current facility. Unknown or ambiguous physical mappings remain unasserted. The existing canonical credit-data registry supplies declared application field bindings; neither the model nor fuzzy name matching invents them.

`policy_grammar.py` supports a conservative initial set of full-sentence numeric requirements and known document requirements. For example:

```text
For term loans, the maximum tenor is 10 years for borrowers rated BBB- or higher.
```

becomes a requirement with:

- `USES_METRIC`: Tenor, bound to `recommended_tenor_years`.
- `CONSTRAINS`: `less_than_or_equal`, `10`, `years`.
- `HAS_SCOPE`: facility equals Term Loan **AND** borrower external credit rating >= BBB-.
- `DERIVED_FROM`: the exact supporting source span, with clause ID and character offsets.

The below-BBB- variant retains a separate `less_than BBB-` condition and a five-year limit. A fragment that omits the facility and might inherit it from surrounding text is left unresolved. Missing or unsupported exceptions, compound requirements, unfamiliar formulas, qualitative qualifications and units are not deleted to make a pattern match.

The graph compiler reads these typed components rather than accepting an LLM-generated inventory definition. It checks allowed edge directions, component cardinality, source reachability, source offsets, literal thresholds/units/scope values, ontology bindings, integrity hashes and grammar equivalence. It rejects an altered threshold, dropped rating condition, missing coverage passage or unaccounted requirement. No source expression is evaluated as code.

## Coverage and last-resort interpretation

Every source passage has a coverage record: `VALIDATED`, `UNRESOLVED`, `LLM_PROPOSED`, `REVIEWED`, or `NON_RULE`. Only narrowly recognized document metadata is automatically classified as non-rule content. Narrative and unknown obligations stay visible until reviewed. A rule count is not a completeness claim.

The initial grammar deliberately does not understand all prose in the current policy collection. On a deterministic check of the stored Tenor Limits and Covenant Package policies, it compiled one current draft per policy and left 136 and 153 passages respectively unresolved. These include narrative and contextual passages, not necessarily that many missing rules. Both example representations are already persisted and can be inspected in the UI. These are synthetic demonstration policies, not BCBS documents or independently validated bank requirements.

The fallback receives only unsupported spans, their unchanged clause context and the constrained ontology. Requirement-like passages are prioritized. The default budget is 20 spans per policy per build, in bounded groups. Neither source passages nor context are silently truncated. Failure, missing quotation, invented literal values, incompatible units or unknown field bindings leave the source unresolved and preserve deterministic results. Successful proposals remain `PROPOSED` and cannot compile. Provider failures can be retried; successful unchanged interpretations are not repeatedly requested.

Configuration:

```dotenv
POLICY_GRAPH_LLM_FALLBACK=true
POLICY_GRAPH_FALLBACK_MAX_SPANS=20
```

Set fallback to false to run a completely model-free build. Deterministic verification of the two stored examples used fallback disabled and made no model calls.

## Review and operational use

The following describes the legacy graph compiler workflow. The current **Policy Evidence**
view uses the current AI extraction records instead; see [AI knowledge cycle](ai-knowledge-cycle.md).
For the legacy compiler API, the workflow was:

1. Build/recompile its representation through the existing background job. The Policy Rule Library shows job progress.
2. Reload the representation and select a source passage to inspect its small graph neighborhood, original quotation and interpretations.
3. A credit analyst/admin can review complete interpretations or record a justified non-rule disposition. The editor preserves AND/OR groups, explicit exclusions and exact source identity. Missing limits cannot be supplied through review.
4. Source interpretation review automatically synchronizes compiled drafts in the same transaction. A second Build/recompile click is unnecessary. Unchanged source semantics reuse the existing version and retain its governance assignments and approval status; changed semantics create a draft revision in the same rule family.
5. Open **Policy Rule Library**, select **Current graph rules**, and open the rule's full details. The **Review this rule** panel combines source verification, relevant dependency decisions, actual data source, operational severity, rationale and explicit confirmation. Choose **Approve rule** after resolving that checklist. Re-reviewing an already approved/active version creates an approved revision, preserving the earlier definition.

Unresolved whole-policy coverage does not automatically block an independent rule. Per-rule dependencies conservatively include source scope, definitions, exceptions, approvals, related limits and unclassified context. These are grouped by source section rather than one approval per passage. Each relevant section requires an authenticated, source-backed decision and rationale. A section that still needs work blocks approval. Reviewers can attach explicitly bound applicability conditions/exclusions; missing request facts remain unknown. Human attestation is required for unsupported prose; graph traversal alone cannot prove its meaning.

Whole-policy coverage remains visible and incomplete assessments cannot report an overall pass merely because a few independent rules are ready. Newly compiled or semantically changed rules start as Draft. Last-resort proposals need explicit source-bound interpretation approval before they can even become compiled drafts. Approving a source interpretation is distinct from approving an operational inventory rule.

At approval and request selection, the backend recompiles the authoritative current graph and compares its output with the stored definition. Governance assignments such as severity and actual data source are distinct from source semantics. Changed source bytes, ontology or rule semantics invalidate eligibility. Unrelated representation bookkeeping does not invalidate an unchanged rule. Relevant dependency interpretation changes invalidate its dependency review snapshot. The library defaults to current graph rules and labels historical records separately, preserving their stored status. Old LLM-first rules remain available historically, but cannot enter operational candidate selection or be newly approved through the legacy path without rebuilding their representation.

Numeric and supported documentary graph-compiled rules are supported. Migration `007_graph_compiled_inventory.sql` extends the inventory predicate without deleting historical rules. The earlier numeric-only startup migration exempts graph-compiled documentary definitions.

## Persistence, audit and concurrency

Representations are shared JSONB records in `credit_data.risk_knowledge_objects`, `kind='metadata'`, payload `kind='policy_representation'`. IDs include the policy version, source checksum and executable ontology/grammar contract. The record contains exact source clauses, span coverage, nodes, edges, proposal state and review history. Compiled inventory definitions carry the representation ID, requirement node ID and content digest; `CPI-RULE-{id}` metadata records their compilation evidence.

The source graph is committed before inventory compilation. Conditional writes prevent an in-flight fallback call from overwriting a concurrent human review. Compilation locks and verifies the current representation and source version before publishing drafts. Reviews lock the representation, require its current digest, derive reviewer identity from authentication, and write both the interpretation and audit event in one transaction. Audit events preserve previous interpretations, new frames and the exact source quote. Source excerpts and character offsets cannot be edited through the review endpoint.

Endpoints, behind existing authentication/CSRF controls:

- `GET /api/risk-knowledge/policy-ontology`
- `GET /api/risk-knowledge/policy-representations/{policy_id}?focus={node_id}`
- `POST /api/risk-knowledge/policy-representations/{policy_id}/review`
- `GET /api/policy-rules?origin=graph|history|all` (defaults to graph).
- `GET /api/policy-rules/{rule_id}/readiness`.
- `POST /api/policy-rules/{rule_id}/approve-reviewed` records dependency decisions and operational approval atomically, rechecking the source and review token.
- Existing `POST /api/risk-knowledge/extractions` builds/recompiles selected policies.

Verification covers deterministic positive examples, rating boundaries, unknown inputs, exact source offsets, document requirements, exceptions, omitted source coverage, graph/threshold/scope tampering, invalid ontology bindings, provider failures, fallback gating and reviewer access. The real stored examples were compiled and their graph API responses read successfully. No real fallback model response was accepted or automatically approved during implementation.

Per-rule dependency review records are shared JSONB metadata under `RULE-DEPENDENCIES-{rule_key}`. Source/checklist digests bind decisions to the reviewed meaning; audit events retain approval snapshots. Request selection uses the reviewed conditions and exclusions. A missing whole-policy scope can only be bypassed for an explicitly reviewed rule context, never as a claim of complete policy extraction.
