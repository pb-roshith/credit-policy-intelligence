# Integration verification

The existing frontend production build passed. The domain and route suite was relocated into the CPI backend's existing tests directory. The normal bootstrap was verified to import only the authoritative workbook, with 4,506 attributes across 197 case-sensitive entities and no manufactured rule or ontology approvals.

The existing PostgreSQL database was reachable. The integrated state route returned the workbook together with the current policy catalog and governed rule totals. Graph projections preserve exact inventory clause evidence and existing rule approval/activation metadata.

Authentication, reviewer permissions, authenticated audit attribution and account-specific request/evaluation namespaces are tested. The complete existing backend/frontend test results are recorded in the implementation handoff. External LLM/Neo4j connections and visual browser QA are not verified.

## NetworkX implementation

The complete backend suite passed: 286 tests run, with 21 explicit skips. New coverage checks the default MultiDiGraph backend, independent provenance for parallel directed relationships, directed approved-rule retrieval, bounded neighborhoods, cycles, invalid graph replacement, isolated snapshots and idempotent catalog projection.

Live API checks against the existing CPI PostgreSQL store confirmed NetworkXGraphRepository, connected catalog graphs, focused rule neighborhoods and the unchanged nodes/edges export contract. Existing policy rule version counts remained unchanged. No frontend changes or new server are required for NetworkX.

## Unified Policy Rule Library extraction

The selected-policy Extract Rules action now queues the Risk Knowledge pipeline. Validation covers explicit policy selection, nine-stage progress, bounded schema/ontology context, source-preserving clause classification, approved-only mappings, unresolved terms, per-version evidence, graph updates and resumable checkpoints. Shared schema initialization is serialized for batch workers, and concurrent proposals cannot overwrite reviewed knowledge.

The complete backend suite runs 304 tests with 22 explicit skips. The frontend has 25 passing tests and its production build passes. The opt-in PostgreSQL test was also run explicitly with mocked model extraction: it exercises policy ingestion, a pre-existing active rule, a new draft, evidence projection, retry without duplication, an edited version, review, activation and restart-state protection. All fixture writes roll back.

Read-only checks of the existing CPI app confirm the integrated library API, connected graph and extraction endpoint. Live rule definitions, statuses, approvals and job counts remained unchanged. No real policy was re-extracted or sent to a model during verification. Live model behavior and visual browser QA remain unverified.
