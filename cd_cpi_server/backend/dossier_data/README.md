# Company list and original documents

This package contains only the MCP company catalog and its original documents.
`companies.json` contains the catalog, source document metadata and checksums.
`files/` contains the actual original PDFs, identified by SHA-256.

Deal records, sections, generated narratives, narrative/version history, audit
history, company context and the sixteen structured financial datasets are not
included. No user accounts, passwords, password hashes, sessions, agents or AI
conversations are copied. The earlier `deals.json` export is superseded and is
removed after the replacement export validates successfully.

## First deployment

1. Include this entire folder on the MCP service, or set `DOSSIER_DATA_DIR` to its
   mounted location. The Dossier backend does not import a data package.
2. Configure the MCP database using `MCP_DATABASE_URL` for Neon. Keep its database
   separate from the Dossier backend database, matching the current architecture.
3. MCP creates its tables and automatically loads the catalog and documents when
   the company catalog is empty. Later restarts preserve existing data.
4. Create/login with the same owner usernames to see their companies. Account
   setup follows the normal registration/administrator workflow; the package
   does not create users or change company ownership.
5. For Gemini, share a persistent `GEMINI_STORE_PATH` between MCP and the backend.
   The original document libraries are restored locally using their existing IDs.

Users can select an imported company and create a new deal. New narratives are
generated through the normal application flow using those source documents.

On Mistral, keep the original provider account: document references are preserved.
Automatic upload into a different Mistral account is not implemented. Gemini
restores the original bytes without requiring the previous Mistral account.
Normal AI operations still require the configured provider credentials.

## Refreshing or validating the package

From `backend`, with its Python environment activated:

```powershell
python -m app.scripts.dossier_data export
python -m app.scripts.dossier_data import-mcp --dry-run
```

Export reads only the MCP catalog/document tables, never the backend deal tables
or financial data tables. It includes all companies, preserving owner usernames,
and reuses verified original files from earlier exports. Missing originals are
retrieved from their provider account. No documents or narratives are generated.
Automatic export is not enabled for this package.

Remove `--dry-run` from the import command to perform an explicit import after
schema setup. A repeat of the same package is a no-op. Conflicting packages and
nonempty target catalogs are rejected. The database import is transactional and
can be retried after a failure. Set `DOSSIER_DATA_AUTO_IMPORT=false` on MCP to
disable automatic startup import.

Preserve this folder and the shared Gemini store in deployment storage. Treat
company documents as private application data. Checksums detect corruption;
only deploy packages from your own reviewed source.
