# Running the copied Credit Dossier components

These folders copy the current Credit_Dossier code and add the Manufacture Data
page, background API, and MCP progress reporting from local branch development-3
(commit 3cb3afc). The original applications are unchanged.

## Ports

- Copied frontend: http://localhost:8081
- Copied backend: http://127.0.0.1:8003
- Copied MCP: http://127.0.0.1:8004/sse

## Setup

Open PowerShell in credit policy intelligence/cd_cpi_server/credit_dossier_backend:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r ..\credit_dossier_mcp\requirements.txt
```

Local .env and protected .data configuration were copied from Credit_Dossier.
The copies currently use the same PostgreSQL databases and Mistral credentials
as the original. Port separation does not isolate database data. Configure
separate DATABASE_URL and POSTGRES_DB values before using independent datasets.
Protected secrets remain tied to the original Windows user; configure them under
that user using the copied backend/scripts tools if needed.

## Start all three copied components

From credit_dossier_backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8003
```

In another terminal, from credit_dossier_mcp:

```powershell
..\credit_dossier_backend\.venv\Scripts\python.exe server.py
```

In another terminal, from credit_dossier_frontend:

```powershell
npm install
npm run dev
```

Open http://localhost:8081 and sign in as a relationship manager or credit analyst.
Choose Manufacture Data, enter company name, industry, and geography, then start
the job. The page shows PDF generation, uploads, table seeding, and the result.
Manufacturing writes synthetic data to PostgreSQL and may call Mistral.

The backend launches manufacturing with its own Python interpreter, so install
both requirements files into the backend virtual environment as shown above.
Build artifacts, uploads, logs, Python environments, and caches are not copied.
