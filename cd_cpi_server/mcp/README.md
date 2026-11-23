# Local Credit Intelligence MCP

This folder replaces the Railway/Azure company-document service with:

- a local MCP SSE server at `http://127.0.0.1:8001/sse`;
- Mistral Document Library storage for 17 manufactured PDFs; and
- local PostgreSQL storage for 16 structured credit tables.

Manufactured PDFs are generated in memory and uploaded directly to Mistral.
The MCP does not retain a local `generated` folder or local PDF copies.

No Railway or Azure service is used.

## Configure

```powershell
cd mcp
Copy-Item .env.example .env
```

Edit `.env` with the local PostgreSQL password and `MISTRAL_API_KEY`.
If `MISTRAL_API_KEY` is omitted, the service also reads the existing
`backend/.env`; values in `mcp/.env` take precedence.

If PostgreSQL is not installed locally, start the included container:

```powershell
docker compose up -d postgres
```

Use `POSTGRES_PASSWORD=local_credit_dossier` in `.env` when using that
container.

## Install and run

```powershell
pip install -r requirements.txt
python server.py
```

The Credit Dossier backend uses the same MCP tools as before:

- `list_companies`
- `retrieve_company_documents`
- `retrieve_company_details`
- `retrieve_company_document_summaries`

The server also exposes 16-table discovery/query tools, an aggregate
`retrieve_company_structured_data` tool, 17 Mistral PDF text tools, and
`manufacture_company_data`. Narrative generation uses the relevant PostgreSQL
tables together with the PDFs when structured rows exist for the client.

## Manufacture data from the command line

```powershell
python manufacture.py `
  --owner-user-id "backend-user-uuid" `
  --company-name "Aster Auto Components Limited" `
  --industry "Auto components manufacturing" `
  --geography "Pune, India"
```

Manufacturing version 2 first creates one shared borrower context so identifiers,
financial values, customers, suppliers, facilities, and collateral remain
consistent across the whole data pack. It then creates:

- 17 document-specific PDFs with 5–8 substantive sections and multiple tables;
- six detailed financial datasets enhanced through the same temporary Mistral
  agent; and
- ten detailed customer, ownership, facility, collateral, covenant, exception,
  and credit-committee datasets.

There are 115 or more manufactured PostgreSQL rows across the 16 tables. Each
table has named business columns in addition to the complete JSON payload.

Manufacturing is idempotent. It reuses the company's existing Mistral Library,
replaces documents created by an older generator version, and refreshes the
company's structured table rows. The Mistral agent is temporary and is removed
after each job. If Mistral generation is unavailable, the same workflow uses a
detailed deterministic fallback.

All generated data is marked synthetic and is intended only for testing.
