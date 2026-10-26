# Governed Policy Rule Inventory

## Repository assessment and implementation plan

The main CPI application is `frontend` (React/Vite) and `backend` (FastAPI,
Pydantic, psycopg/PostgreSQL). The Credit Dossier application under
`cd_cpi_server` supplies account-scoped deals through its existing shared
API; it is not another policy store. Existing user authentication, CSRF handling,
shared policy connections and account RLS are reused.

Policy metadata is in `credit_data.policy_documents`. Generated sources are in
`backend/generated_policies`; imported DOCX sources are in `backend/policy doc`.
Existing absolute source paths can refer to an older workspace. Ingestion resolves
registered filenames in these configured directories, without accepting browser
paths. The current database contains 25 PDFs and 10 DOCX policies.

Existing credit entities are `user.credit_requests`, `borrower`,
`credit_request_compliance`, `credit_request_policy_evaluations`,
`ai_compliance_reviews` and `credit_request_exceptions`. Shared Dossier requests
remain read-only, with missing values preserved rather than taking the display
assumptions used by the workbench. Existing scoring and exception workflows are
retained. Saved historical AI assessments remain accessible.

The original rule implementation extracted summaries, auto-activated approvals,
stored definitions as JSON and supported six direct comparisons. The replacement
adds actual source ingestion, normalized provenance, strict Mistral extraction,
explicit activation and deterministic checks with unresolved outcomes.

Implementation sequence: schema/migration; ingestion/extraction; governance;
applicability/execution/explanation; UI/reporting; tests and configuration.

## Exact modules

- `backend/app/migrations/001_governed_inventory.sql`: repeatable migration.
- `backend/app/rule_store.py`, `bootstrap.py`: existing-table upgrade and account security.
- `services/policy_ingestion.py`: PDF/DOCX/text parser, checksums, source archives, clauses.
- `services/inventory_schema.py`: typed, extra-field-forbidden extraction and review schemas.
- `services/rule_extraction.py`: Mistral agent, validation, checkpoints, jobs, reports.
- `services/rule_governance.py`: version creation, proposed-rule edits, lifecycle and audit.
- `services/request_applicability.py`, `rule_engine.py`: structured three-valued conditions and calculations.
- `services/rule_assessment.py`: normalized account-owned assessments and immutable snapshots.
- `services/rule_explanation.py`: Mistral narratives after deterministic results, with safe fallback.
- `routers/rules.py`, `routers/compliance.py`: inventory, review, source, generation and history APIs.
- `frontend/src/pages/RuleLibrary.jsx`: real inventory, details, filters, governance and progress.
- `frontend/src/pages/AdminDashboard.jsx`: administrator inventory-generation access.
- `frontend/src/pages/Compliance.jsx`: all outcomes, source evidence, calculation and version trace.
- `backend/app/scripts/generate_rule_inventory.py`: repeatable initial draft-generation CLI.

## Data relationships

`inventory_policies` → `policy_versions` → `inventory_documents` → `policy_clauses`.
`policy_rule_entities` → `policy_rule_versions` links the logical rule to the exact
policy version and clause. Separate children store applicability, inputs, evidence
requirements and AND/OR/duplicate relationships. Reviews and audit events preserve
actor, decision, reason, previous/new state and timestamps.

The old `policy_rules` table becomes `policy_rule_versions`; `policy_rules` remains
an updatable compatibility view. Existing primary keys, audit references and rule
snapshots are preserved. Legacy rules without source provenance require a revised
draft bound to an ingested clause before operational activation.

Account RLS protects `rule_assessment_runs`, `policy_request_mappings`,
`request_rule_assessments` and `assessment_evidence`. Every finding has a foreign
key to the exact logical rule, rule version, policy version and clause. A saved
review is reused unless the user explicitly requests reassessment; new versions
never rewrite old assessments. Rule details show only the current user's assessments.

## Extraction and source handling

PDF uses pypdf and preserves physical page numbers. DOCX uses inert ZIP/XML parsing,
preserves headings and table-row text, and reports pages as unavailable. UTF-8 text
preserves paragraph/numbered-clause spans. XML entities, encrypted/no-text PDFs,
unsupported types and oversized/expanded files are rejected. Registered local
files only are processed; source copies are archived by SHA-256 checksum.

Mistral receives source clauses as data under a fixed system instruction with no
tools. `chat.parse(response_format=ExtractionOutput)` produces typed output;
free-form prose is never inserted. Server identity/status fields cannot appear in
AI output. Thresholds must occur explicitly in an exact source span. Missing
properties remain null and are recorded in `missing_information`. Whitespace-only
PDF quote differences are restored to the original source text; paraphrases fail
validation. Duplicate candidates are flagged, never merged.

Clause-batch checkpoints and deterministic extraction keys prevent duplicate
retry drafts. Source version/checksum changes invalidate current provenance and
require extraction and business review. Partial failures retain completed batches. AI-generated rules from incomplete extraction cannot be approved until the source processing completes.
Jobs have per-policy progress, bounded retries with smaller-group fallback, sanitized failure codes and a
report. A stale interrupted job can be retried after 30 minutes. Agent logs record
execution ID, model, prompt version, attempt, status and timing, not hidden reasoning
or full document prompts.

## Governance and execution

Draft → Under Review → Approved → Active → Inactive → Active; Retired and Rejected
are separate outcomes. Approval does not activate. Credit analysts and admins
review, approve, reject, activate, deactivate and retire. Proposed edits retain the
version and audit old/new values. Changes to approved/active/inactive/retired rules
create a new Draft version with a superseded-version reference. Active periods of
the same logical rule cannot overlap. No production seed rules are auto-approved.

Managed conditions support AND/OR and request fields including segment, facility,
geography, sector, borrower type, amounts, exposure, currency, collateral, rating,
risk and stage. Missing applicability data yields Unable to Determine Applicability.
Only approved Active versions in the current source version and effective period
are retrieved. Policy mappings record applicability and the reason.

Deterministic operators: equals/not-equals, ordered comparisons, between, in/not-in,
exists/does-not-exist. Calculations: direct, ratios, percentages, date age in days,
document inventory presence, approval-authority comparison, compound conditions,
and manual judgment. No eval or executable calculation string is supported.
Explicit known document absence may breach; missing inventories or inputs cannot
pass. Conflicting evidence requires manual review. USD/INR and other named currency
units are not interchanged; explicit thousand/million/billion units are normalized
by application code. FX conversions require a separately approved mapped input.

All six outcomes are stored and displayed: Pass, Warning, Breach, Not Applicable,
Unable to Assess, Manual Review Required. A score is withheld if unresolved checks
remain. Mistral explains completed deterministic findings without doing arithmetic.
Invalid/failed narratives use a deterministic evidence-based explanation, retaining
the original result and recording the provider failure.

## Configuration and use

Install `backend/requirements.txt`, set existing `DATABASE_URL`, `MISTRAL_API_KEY`,
`MISTRAL_POLICY_MODEL` and `MISTRAL_TIMEOUT_MS`, then restart the backend. Startup
applies the repeatable migration transactionally and configures RLS. No manual SQL
schema editing is needed. The existing database user needs bootstrap DDL privileges.

Additional variables:

- `RULE_MAX_FILE_BYTES=20971520`: source limit (20 MiB).
- `RULE_CLAUSE_BATCH_SIZE=4`: 1–10 clauses per batch, also capped by text size.
- `RULE_EXTRACTION_RETRIES=2`: 1–3 attempts.
- `RULE_INVENTORY_WORKERS=2`: 1 to 4 concurrent policy workers.
- `APP_ENV=production`, `RULE_DEMO_AUTO_APPROVE=false`: secure defaults.

For a demo only, both `APP_ENV=development` and `RULE_DEMO_AUTO_APPROVE=true` are
required. An admin must explicitly select a manufactured synthetic rule and use
its labelled demo approval action. Validation still applies and activation is
separate. Imported real documents cannot use this action.

Administrators: open Admin Dashboard → Policy Rule Inventory → Generate Rule
Inventory from Policies. Analysts: Policy Intelligence → Policy Rule Library →
select policy → Extract selected policy. Review each draft, confirm thresholds,
data sources and operational severity, submit, approve, then activate. Use the
Compliance screen for request assessment. Expand findings for exact evidence,
inputs, calculations, missing fields and rule versions.

CLI from backend:

```powershell
.\.venv\Scripts\python.exe -m app.scripts.generate_rule_inventory --report inventory-extraction-report.json
```

Use repeatable `--policy-id` arguments to restrict an administrative run. Report
fields include processed/failed policies, clauses, proposed/quantitative/qualitative
rules, manual-review rules, missing thresholds, validation failures and duplicate
candidates. `backend/inventory-extraction-report.json` is the actual generation
report; the generation screen also provides downloadable reports.

## API overview

- GET `/api/policy-rules`, optional `policy_id`.
- POST `/api/policy-rules`; PUT `/api/policy-rules/{version_id}`.
- POST `/api/policy-rules/{version_id}/actions` with action and reason.
- GET `/api/policy-rules/{version_id}/details` and `/audit`.
- GET `/api/policies/{id}/clauses`.
- POST `/api/policies/{id}/propose-rules`: analyst/admin per-policy background job.
- POST `/api/inventory/generate`: admin bulk job, optional policy_ids.
- GET `/api/inventory/jobs` and `/jobs/{id}`.
- GET `/api/inventory/documents/{id}/source`: authenticated archived source.
- GET `/api/inventory/config`; POST `/api/policy-rules/{id}/demo-approve`.
- POST `/api/compliance-review/run`: cached assessment unless recalculate=true.
- GET `/api/compliance-review/history/{review_id}`: account-scoped historical review.

## Verification

Run backend unit tests from backend:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Run the transactional PostgreSQL suite against the bootstrapped test/development
database (all fixtures roll back; no approved test rules remain):

```powershell
$env:RUN_INVENTORY_DB_TESTS='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The end-to-end test uses the real parsers, PostgreSQL schema, review service,
activation, account RLS, mapping and execution with a typed fake Mistral response
for deterministic testing. Initial inventory generation uses the real Mistral API.
Frontend: `npm run build`, `node --test tests/*.js tests/*.mjs`.

## Assumptions and operational limits

- Review permission uses existing credit analyst/admin roles; no new identity system.
- Existing catalog documents are the policy identities. Effective dates are taken
  from stated ISO or unambiguous named-month dates where available, otherwise labelled catalog metadata.
- DOCX/text pagination is unavailable; scanned PDFs require OCR before ingestion.
- Request data uses actual Dossier intake fields and known CPI synthetic data.
  Supporting document/approval/human evidence absent from those sources remains
  unresolved. This change does not fabricate uploads, FX rates or human judgments.
- Legacy exception creation remains tied to local CPI requests; Dossier exceptions
  require the separate existing canonical-request integration.
- Background jobs use bounded worker threads within the existing FastAPI process,
  durable database checkpoints and stale-job retry; there is no external queue.
- Source archives must be retained with the database for historical document access.
- Human review is essential for source semantics, duplicate candidates, ambiguity,
  qualitative requirements and model-proposed field mappings.

Verified in the working database: 35 source documents ingested, 1,609 preserved
source spans, real Mistral-generated Draft proposals. The downloadable sample
report is [sample-extraction-report.json](sample-extraction-report.json). Bulk
extraction is asynchronous; its full report contains per-policy validation
failures and retry status. No proposal is approved or activated by generation.

Validation completed: 72 backend tests (including 8 transactional PostgreSQL tests),
10 frontend tests, Python compilation and the Vite production build.
