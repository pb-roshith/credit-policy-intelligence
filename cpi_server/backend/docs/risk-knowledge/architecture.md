# Integrated architecture

The existing `cpi_server/backend/main.py` registers the authenticated Risk Knowledge router alongside current policy, rule, request and compliance routers. The existing Policy frontend page renders the feature inside its Risk Knowledge tab.

Source workbook ? exact source taxonomy ? proposed enrichment ? human review ? approved ontology.

Existing CPI policy catalog + governed rule versions + exact inventory clauses ? read-only graph projection with edge provenance.

Additional source uploads ? classified clauses ? structured candidate extraction ? approved-taxonomy mapping ? validation ? human review. These supplemental objects are separate from operational rule activation. Operational catalog rule review and activation remain in the existing Policy Rule Library.

The graph reconstructs source containment and explicit relations. It does not infer edges from co-occurrence. Each displayed edge contains provenance. Existing governed rules retain exact source versions and active/review flags, and are never passed into a different expression engine by reinterpretation.

The shared PostgreSQL table stores typed JSON objects. Source/taxonomy/ontology objects use a shared namespace. Supplemental request and evaluation results use the authenticated owner's namespace. Reviews append to the existing audit table. Uploaded file bytes use the existing inventory_sources archive beneath the CPI backend.

The deterministic expression evaluator and NetworkX graph repository remain modular. A `MultiDiGraph` preserves directed, parallel relationships with independent provenance. Approved knowledge-rule retrieval follows incoming DERIVED_FROM edges at exact source clauses. Explorer focus uses NetworkX shortest-path lengths over an undirected view, limited to two hops; the underlying graph retains edge direction. Graph replacement validates the complete projection before publishing it. PostgreSQL remains authoritative, and exports retain the existing nodes/edges JSON contract.

Numeric comparison uses Decimal, rating order requires approved taxonomy metadata, and missing evidence yields INSUFFICIENT_DATA. Existing CPI request assessment continues to use its original governed rule engine and controls.

Six independent LLM tasks are specified in llm-contracts/. The default mock provider makes no network calls; external output cannot grant approval. Unknown source metadata stays UNKNOWN. Normal initialization does not load test fixtures.

## Selected-policy orchestration

`risk_knowledge/pipeline.py` owns the library extraction workflow. Existing inventory jobs dispatch each selected policy to this orchestrator. It prepares source knowledge, classifications and ontology candidates before calling the existing structured extraction adapter with bounded reviewed context. Original policy fields and source wording are preserved; normalization is stored separately.

Each persisted governed rule version receives metadata under `CPI-RULE-{version_id}`. The normal library and catalog SQL join this evidence, and graph projection creates MAPS_TO edges only for concepts that remain APPROVED. Candidate ontology assertions never gain approval through extraction. API progress persists all nine stages per selected document, including failures. Checkpoints include the pipeline knowledge-context fingerprint; retries restore missing annotations without duplicating completed batches.

Risk Knowledge rules have a recognizable extraction-key namespace and explicit Draft/inactive state. Assessment queries exclude unreviewed candidates while retaining a previous active version. The review workflow and bootstrap migration protect these states across restarts. These rules share the existing inventory, human audit, source archive and activation controls; the workflow does not copy them into the supplemental knowledge-rule store.
