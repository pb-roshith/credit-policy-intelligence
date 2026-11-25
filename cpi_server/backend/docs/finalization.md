# Solution finalization: semantic workflow

Release: `semantic-finalization-v1`, 12 November 2026.

The active screens use current taxonomy, ontology 1.2.0, semantic extractions and the published knowledge graph. Earlier extraction/compiler results remain stored but do not supply current policy requirements, graph rules or request assessment scores. Manufactured controls and exceptions are available as explicitly labelled workflow data.

## Corpus and review state

| Item | Current count |
|---|---:|
| Registered / processed policies | 35 / 35 |
| Current source passages | 1,609 |
| Extracted rules | 1,078 |
| Published graph rules | 863 |
| Proposed rules | 215 |
| Extracted qualitative / quantitative rules | 763 / 315 |
| Published qualitative requirements (controls) | 721 |
| Approved / pending policy scopes | 19 / 16 |
| Unresolved passages | 159 |
| Failed extraction batches | 0 |
| Graph nodes / relationships | 3,622 / 7,246 |

Processing all documents does not imply every rule or policy scope is approved. Proposed rules, unresolved passages and incomplete scope continue to appear in review. They cannot silently become applicable rules or passing assessments.

## Consistency contract

1. Policy library, source evidence and taxonomy use registered current policy documents and passages.
2. Rule library contains only current semantic extractions. Graph membership is explicit: validated approved rules with satisfied dependencies.
3. Published policy requirements use qualitative rule IDs and exact evidence. Mapped Controls and the controls register show generated control records only, with each submission adding to the existing per-policy total. Related policies use normalized source-backed concept values and recorded parent-document membership, with reasons shown and no fabricated match percentages.
4. Request assessments use deterministic graph traversal. Saved reviews must have the current engine and knowledge fingerprint; request-specific latest-review retrieval also checks the request fingerprint.
5. Request lists and dashboards use current graph assessment scores. Manufactured legacy scores and rating-based UI score guesses are excluded. No assessment means Not assessed; incomplete assessment means no numerical score.
6. Exceptions created manually from Compliance Review must reference a matched current assessment rule. A server-generated knowledge context identifies their graph snapshot. Registry, dashboard and portfolio use the same exception projection and retain account row permissions. Explicit Data Manufacturing exceptions are included and labelled synthetic; earlier unlabelled records remain outside those current views.
7. Insights require the current knowledge fingerprint. Policy Copilot uses the current graph and validates retrieved rule citations. Provider names in active screen copy are neutral.
8. Scenarios remain account- and request-scoped. Unlinked historical scenarios are excluded from the active UI. Financial simulation assumptions remain labelled and are not presented as extracted policy requirements.
9. Observability includes semantic extraction/matching explanation operations and new calls from supported features. Retired extraction operations and earlier demo telemetry stay stored outside the active view.

## Removed active entry points

The older uploaded-document extraction, vocabulary-enrichment, stored-relationship review, numeric-rule editing and standalone demo-evaluation actions under `/api/risk-knowledge` return HTTP 410. Compatibility graph, representation and export reads resolve to current semantic projections. The policy-control and exception generators in Data Manufacturing were restored on 13 November 2026. Manual exception creation also remains available from Compliance Review.

The spreadsheet remains a source reference dictionary. Taxonomy suggestions do not establish policy applicability. Older implementation modules remain available for audit and regression coverage; active navigation does not expose their datasets.

## Verification

`dm_server/seed_others/outputs/finalization/consistency-report.json` records 41 read-only corpus checks, including every policy's expandable rule view, source references, graph/schema conformance, and equality between published library rules and graph rule IDs. The release manifest hashes the refreshed taxonomy, ontology and populated graph artifacts.

The graph and ontology exports were regenerated from existing records without extracting policy text again. Superseded demonstration files, retry checkpoints and ontology packages were moved to `dm_server/seed_others/outputs/archive/superseded-artifacts`. No policy source, historical rule or account audit record was deleted.

Regression validation: backend suite ran 544 tests successfully (28 skipped); frontend suite passed 57 tests; Vite production build passed. JSON Schema, RDF/Turtle, SHACL positive validation and a negative incompatible-unit case passed. The 41 corpus consistency checks all passed. Account exception creation/isolation/analyst-approval integration uses rolled-back writes and passed. No live LLM extraction was run during validation.

Authenticated read-only HTTP smoke checks passed for 13 current endpoints: workspace state, semantic rule inventory, schema, expandable graph, policy evidence, taxonomy, controls, requests, exceptions, dashboard, observability, current assessment summaries and shell summary. No response contents or account identities are included in the report.

## Data Manufacturing restored, 13 November 2026

Users can generate 1-5 manufactured controls per policy and one manufactured exception per selected authorized credit request. Generated controls are available through Policy Intelligence > Controls > Manufactured controls and the policy-specific mapped-controls panel. The published-policy-requirements view continues to show the semantic rules. Generated exceptions retain account ownership, appear in the registry and aggregate views, and carry explicit synthetic/Data Manufacturing provenance. Generated records do not publish rules into the knowledge graph. Generator and register integration tests use rolled-back transactions.

The 13 November control-count correction removes extracted qualitative requirements from the Mapped Controls total. Verified five generated controls for each of all 35 policies without regenerating data. Related-policy discovery now joins typed concept values across policy-scoped node IDs and includes recorded parent-policy membership. It excludes generic taxonomy categories and unknown parent values. Relationships and controls load independently so a failure in one panel cannot clear the other.

Control generation is append-only. Each submission adds 1-5 controls per policy, under an advisory transaction lock, starting after the highest existing sequence. Existing controls are neither deleted nor updated. Database sequence constraints allow totals above five. Response `added_count` distinguishes the new records from total `control_count`. Rollback integration coverage verifies consecutive submissions of five then two and checks every pre-existing row remains unchanged.

## Dedicated Data Manufacturing application

Data Manufacturing now lives in `dm_server/frontend` with its own API entry point in `dm_server/backend`. Open UI port 5174 and API port 8005. CPI retains its other pages on 5173/8002 and no longer mounts generation endpoints or navigation. Common identity, authorization, data services, login UI and styles are reused, with separate application-scoped sessions and cookies. The shared store preserves generated-data availability in CPI. Setup and verification are documented in the [workspace run guide](../../../run.md#data-manufacturing).
