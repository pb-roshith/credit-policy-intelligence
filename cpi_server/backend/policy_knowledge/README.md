# Portable policy knowledge

`knowledge.json` contains the current shared policy catalog, extracted rules,
source passages, taxonomy/ontology objects, policy scope, review decisions and
embedded review history. It excludes customer accounts, requests, deals,
assessments, API keys, provider resource IDs and provider conversations. It is a
deployment seed, not a database backup or a full historical audit-log export.

The knowledge graph is reconstructed and validated from the imported records.
Only eligible approved rules enter the graph. Proposed/rejected rules, unresolved
passages and incomplete scopes retain their existing states.

## Export locally

From `cpi_server/backend`, with its Python environment activated:

```powershell
python -m app.scripts.policy_knowledge export
```

The CPI backend automatically refreshes this package when shared policy knowledge
changes, checking every 15 seconds. This covers extraction, rule reviews, scope,
catalog, source passage, taxonomy and ontology changes. Changes across processes
are detected from committed database snapshots. Unchanged knowledge is not
re-exported. The manual command remains available for an immediate export.

Export reads the database without changing it and atomically replaces this
folder's knowledge file. The file contains a checksum and format/ontology/pipeline
versions. Checksum validation detects corruption, not an untrusted publisher;
deploy packages from your own reviewed source tree.

The automatic worker retries failures and keeps the previous valid package;
errors are logged on the backend. A clean shutdown attempts a final refresh.
Set `POLICY_KNOWLEDGE_AUTO_EXPORT=false` to disable it, or
`POLICY_KNOWLEDGE_EXPORT_INTERVAL_SECONDS` to change the interval. Restart CPI
after installing this change to start the worker. No AI calls are involved.

Locally, files update in this folder. On Railway, set
`POLICY_KNOWLEDGE_EXPORT_DIR` to a directory on a persistent volume to retain
automatic exports across redeployments. Automatic export does not commit/push
files to Git or copy them to another machine. Include the latest package in a
future fresh deployment. Fresh-database automatic import still reads the bundled
`backend/policy_knowledge` folder; the export-directory setting controls writes.

## First deployment

Include this folder, `generated_policies/*.pdf`, `policy doc/*.docx`, and the schema
workbook `risk_schema/Risk Data Model_Oct 2026.xlsx` in the deployment. The PDFs are
allowed by the repository's `.gitignore`; ensure they and the JSON are committed
when deploying through Git.

On CPI startup, after database setup, the packaged catalog and knowledge load
automatically **only if the policy catalog is empty**. Do this before generating
or importing policy documents through Data Manufacturing. No AI calls, document
regeneration or rule extraction are needed. Local file paths are resolved on the
new server; previous hosted provider resources are deliberately not transferred.

Use a fresh Neon database with the schema permissions required by the application.
This feature does not change those existing deployment requirements.

To disable automatic loading, set `POLICY_KNOWLEDGE_AUTO_IMPORT=false`. To run the
same import explicitly after schema setup:

```powershell
python -m app.scripts.policy_knowledge import --dry-run
python -m app.scripts.policy_knowledge import
```

The importer verifies every deployed document checksum, source/evidence identity,
record digest and ontology conformance. All database inserts occur in one
transaction. A missing/changed document or incompatible package stops the import.
Serial source IDs are preserved and database sequences advanced accordingly.

An explicit repeat of the same package is a no-op. A different package or an
already populated policy catalog/inventory is rejected. Normal application
restarts skip seeding populated catalogs and preserve subsequent edits. Loading
updated packages into an operational database requires a separate migration;
this importer never merges or replaces existing policy knowledge.
