# Risk Knowledge in CPI

Risk Knowledge runs behind the existing Policy Rule Library in `cpi_server`. Users select policies and click Extract Rules. The separate Risk Knowledge tab and technical progress notices are hidden. The existing frontend uses port 5173 and FastAPI uses port 8002.

## Location

- Backend domain and services: `backend/app/risk_knowledge/`.
- Existing API router: `backend/app/routers/risk_knowledge.py`, registered by `backend/main.py`.
- User interface: the existing `frontend/src/pages/RuleLibrary.jsx`; knowledge processing runs internally.
- Authoritative workbook: `backend/risk_schema/Risk Data Model_Oct 2026.xlsx`.
- Tests: `backend/tests/risk_knowledge/`.
- Documentation and LLM schemas: `backend/docs/risk-knowledge/`.
- Runtime source archives: the existing `backend/inventory_sources/risk_knowledge/` directory, Git ignored.

## Install and run

Use the existing `cpi_server/run.md` or root `start_all.bat` flow. Update dependencies once:

```powershell
cd cpi_server/backend
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8002
```

In another terminal, start the existing frontend:

```powershell
cd cpi_server/frontend
npm run dev
```

The existing virtual environment includes openpyxl, python-multipart and NetworkX. No new frontend dependency is required. PostgreSQL connection settings and environment loading remain in the existing backend `.env` and configuration module.

## Data and governance

The initial source model contains 197 exact entity names and 4,506 attribute records. The workbook remains unchanged. Auxiliary worksheet data is retained; undeclared data types, FK targets, domains and vocabularies remain UNKNOWN. AI proposals are distinct objects and never replace their source parents.

Normal initialization imports only this workbook. It does not load manufactured policies, borrowers, ratings, rule approvals or reference documents. Synthetic fixtures are invoked explicitly by isolated tests only.

The source assets and policy graph read the existing CPI policy catalog and latest governed rule versions. No policies, rule approvals or active statuses are copied into a competing operational library. Exact existing clauses establish DERIVED_FROM edges; missing clause links are not fabricated. Catalog summaries are explicitly distinguished from extracted wording. Existing rules retain their source version, active flag and review-required metadata. Governed rules are visually identified separately from optional supplemental extraction candidates.

## One-click extraction from Policy Rule Library

Select a policy in the library dropdown and click **Extract Rules**. For a batch, leave the dropdown on All policies and explicitly check the documents to process. Both the new `/api/risk-knowledge/extractions` endpoint and the existing inventory extraction endpoints use the same Risk Knowledge worker and durable inventory jobs.

The pipeline automatically prepares schema/taxonomy context, proposes vocabulary enrichment, ingests the selected policy, classifies clauses, discovers supported ontology candidates, extracts structured rules, maps terminology, validates provenance and updates the NetworkX policy graph. The existing typed Mistral extraction agent receives bounded source-schema, approved taxonomy and approved ontology context. Vocabulary context cannot introduce policy requirements or thresholds.

Results are saved directly into `policy_rule_versions`. Source passages, mappings, validation checks and context fingerprints remain in backend records. The user sees Completed and the extracted rule count whenever rules were saved, including after a clause-group failure.

Eligible taxonomy concepts and relationships are approved automatically, with system attribution in audit records. Rejected objects are preserved. Ontology endpoints must be approved. Unmatched terms remain unresolved internally; automatic approval does not fabricate mappings or source thresholds.

Source-backed extractions are automatically approved under `system:auto-approval`, including saved results after a group failure. Existing saved candidates use the same approval policy. Source validation remains mandatory. Approval is distinct from activation; source, executable-input and overlap checks still apply to activation. Restart migrations preserve these states.

Existing Credit Requests, Compliance Review and Decision Simulator remain the operational workflows and consume reviewed active Risk Knowledge versions. Automatic extraction does not make a credit decision. Additional direct source uploads remain available for reference/knowledge work; the selected-policy library action is the integrated catalog workflow.

## Persistence and security

The existing PostgreSQL connection stores knowledge objects in `credit_data.risk_knowledge_objects`. Migration `006_risk_knowledge.sql` is picked up by the existing bootstrap migration runner. Reviews append to the existing `credit_data.audit_events`. SQLite is used only for isolated tests, not by the integrated router.

All `/api/risk-knowledge/*` routes require the existing authenticated CPI session. Mutations require a credit analyst or administrator. CSRF verification, request handling and CORS use existing infrastructure. Reviewer attribution comes from the authenticated session, rather than a submitted name. Private supplemental request/evaluation records are keyed by authenticated owner, while source taxonomy/ontology is shared policy knowledge.

The frontend uses the existing API client, including cookies and CSRF. The client now lets the browser set multipart boundaries for FormData uploads. Scoped feature CSS uses the existing CPI theme and cannot restyle the rest of the application.

## LLM and graph configuration

Runtime defaults to `LLM_PROVIDER=mistral`: supporting classification, taxonomy, ontology and mapping tasks use the existing `MISTRAL_API_KEY`, `MISTRAL_POLICY_MODEL` and timeout. `LLM_PROVIDER=mock` is an explicit isolated-test/demo option, and SQLite test services default to it. A compatible external endpoint remains available through `LLM_PROVIDER=external`, `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`. Ontology endpoints are constrained to supplied concept IDs and supporting quotations must match source text. Retrieval filters common words and weights financial terms. No keys are exposed to the frontend.

`app.risk_knowledge.enrichment.enrich_saved_policy` refreshes existing rule versions without rule extraction or duplicate versions. `reuse_mappings=True` revalidates saved mappings and refreshes ontology links. Explicit old-extraction cleanup writes a backup under `backend/inventory_sources/risk_knowledge/backups`, refuses to delete assessed versions, and records cleanup in the audit history. It is never run on startup.

The graph defaults to `NetworkXGraphRepository`, backed by a directed NetworkX `MultiDiGraph`. Multiple relationships between the same nodes retain their own IDs, statuses and source evidence. NetworkX performs source-clause traversal for approved knowledge rules and bounded neighborhood exploration for the graph UI. The existing JSON graph API and React visualization remain unchanged. PostgreSQL remains the runtime record store; no graph server is required. See the [NetworkX graph documentation](https://networkx.org/documentation/stable/reference/classes/multidigraph.html).

An optional Neo4j adapter mirrors the NetworkX projection into the dedicated CPIPrototype namespace. Install the neo4j driver and set NEO4J_URI/USER/PASSWORD only if that mirror is wanted. No automatic precedence is inferred from overlaps or superseded status.

## Verification

```powershell
# From cpi_server/backend
.venv/Scripts/python.exe -m unittest discover -s tests -q
# From cpi_server/frontend
node --test
npm run build
```

Tests cover numerical/rating logic, missing information, AND/OR, exceptions, source fidelity, schema parsing, approval/edit gates, existing catalog projection, authentication, role restrictions, reviewer attribution and account isolation. Runtime schema initialization and catalog reads were checked against the existing PostgreSQL database. Browser visual QA, live external LLM calls and a configured Neo4j service are not verified.
