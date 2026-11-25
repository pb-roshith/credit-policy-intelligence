# Initial inventory generation and business review

The initial run discovers the configured generated-policy and source-document
directories plus existing registered local document paths. Immutable source
archives are excluded from discovery to avoid re-registering copies.

The current repository has 25 manufactured PDFs and 10 registered source DOCX
policies. All 35 are included. Existing successful Mistral extraction checkpoints
are reused; interrupted or failed policy documents resume through the current
strict extraction agent. Previous rule versions and assessment records remain
in place. No extracted records are manually fabricated.

## Run and monitor

In **Admin → Policy Rule Library**, expand **Discovered policy documents** to see
files, source types, registration, availability and retry information. Click
**Generate Rule Inventory from Policies**. The same inventory is available under
Policy Intelligence to business reviewers. Jobs show extraction progress, summary
counters and quality-review progress, and refresh while running.

From the backend directory:

```powershell
.\.venv\Scripts\python.exe -m app.scripts.generate_rule_inventory --report ../../dm_server/seed_others/outputs/inventory-reports/initial-inventory-report.json
```

This performs discovery/registration, source ingestion, clause-group Mistral
extraction, schema/source validation, Draft storage, duplicate comparison and
quality review of every current Draft/Under Review version selected for the job.
The CLI logs each discovered file and creates the summary plus
`initial-inventory-report-exceptions.json` when processing finishes.

Already registered documents retain their supplied catalog metadata. A newly
discovered local file without catalog metadata is registered as **Pending Metadata**
with explicitly unresolved version/category and a local registration identifier.
Its catalog date is a registration date, not an inferred policy effective date.
Business metadata validation is required before that policy can become operational.
Source excerpts, dates and page references remain governed by source ingestion.

## Failure handling and quality review

Failed clause groups do not stop other groups or discard their valid Drafts.
Each failed group retains its clause identifiers, attempt number, validation
error and **Retry available** status. Successful retry checkpoints are reused;
resolved failures remain in the ledger marked **Resolved by retry**.

Quality Review Agent calls use bounded groups with separate source clauses and
exact rule-version identities. Responses must include every supplied rule exactly
once. Unsupported duplicate identifiers or malformed reports reject the batch.
Rules stay Draft regardless of the advisory quality result. Successful reports
and failed reviews are saved, including snapshot checksums and execution logs.
Changing a Draft invalidates its previous quality report. Rerunning inventory
reuses successful reviews of unchanged versions and retries failures.

The review screen exposes **UNSUPPORTED**, **REVISION_REQUIRED**, acceptable,
failed, missing and stale quality outcomes through filters and badges. Missing
information/ambiguities and duplicate relationships are visible beside each rule.
Duplicate flags are candidates for human judgment, not automatic merging.
Similarity comparison covers rules within a policy; model duplicate review covers
the supplied batch. Neither claims an exhaustive semantic comparison of every pair
across the entire library.

Use **Download exception report** on the job to download batch errors, failed agent
attempts, earlier extraction failures, quality findings and unresolved rules.
Failures remain visible even when a later attempt succeeds. Summaries distinguish
newly proposed rules from the total stored inventory, including retained versions.

## Explicit synthetic demonstration approval

For a credit analyst or administrator:

1. Inspect the source and quality report, then edit any unresolved mapping needed
   for the check. Never supply a numeric policy limit absent from the source.
2. Expand chosen manufactured rules and tick **Select this rule version for
   demonstration review**. Selection is explicit and limited to 50 versions.
3. Enter a business review rationale and click **Submit selected for review**.
4. Click **Approve selected (inactive)** after business validation.
5. Click **Activate selected** when the selected approved versions should operate.
6. Click **Reassess my synthetic requests** to append fresh account-scoped reviews.

These controls require an authorized human action. They do not depend on, enable,
or invoke the development auto-approval flag. Imported policies cannot be selected
through this synthetic demonstration batch endpoint; their normal individual human
review workflow remains available. Each selected transition has its own audit
event, source/readiness checks and per-rule success/failure result.

Rules with failed/incomplete extraction cannot be approved until source processing
is complete. Numeric limits must retain exact source support at approval. Missing
data cannot produce a Pass, and checks needing expert judgment remain Manual Review
Required. Human approval never means AI approval of an exception or credit request.

## Assessment preservation

Reassessment uses only approved Active, effective, current rule versions. Policy
mappings and normalized findings store exact policy/rule/clause version identifiers
and evidence. Every rerun appends a new saved review; historical reviews and original
version references are preserved. Request processing uses account row-level security
and does not reassess another account's requests. Failures are returned per request.

With no human-approved active rules, the reassessment action returns **Awaiting
human approval and activation** and creates no findings. This is the intended
boundary for the initial run; selecting rules for approval is a business decision.

## API additions

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/inventory/documents` | Current discovery list |
| GET | `/api/inventory/jobs/{job_id}/exceptions` | Downloadable JSON exception report |
| POST | `/api/inventory/selected-demo-rules/actions` | Explicit selected submit/approve/activate with rationale |
| POST | `/api/inventory/assess-synthetic-requests` | Append assessments for the caller's synthetic CPI requests |

Migration `002_inventory_operations.sql` is applied through the existing repeatable
startup migration runner. It adds job discovery/review progress, extraction attempt
records and snapshot-bound quality reports. It changes no historical assessment
identities or approval statuses.
