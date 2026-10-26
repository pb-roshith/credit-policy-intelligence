# Run Credit Dossier CPI

Requires Python 3.10+, Node.js compatible with Vite 8 (20.19+ or 22.12+), and a running PostgreSQL server.

Project folder: `C:\Users\2863775\Documents\CRO_Solutions\credit policy intelligence\cd_cpi_server`.

## 1. First-time setup

Open PowerShell and install the Python dependencies into one shared environment:

```powershell
cd "C:\Users\2863775\Documents\CRO_Solutions\credit policy intelligence\cd_cpi_server\credit_dossier_backend"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r ..\credit_dossier_mcp\requirements.txt
```

Install frontend dependencies:

```powershell
cd "C:\Users\2863775\Documents\CRO_Solutions\credit policy intelligence\cd_cpi_server\credit_dossier_frontend"
npm install
```

If setup is already complete, skip this section.

To provision the isolated CPI databases with the configured local PostgreSQL
credentials, run from `credit_dossier_backend`:

```powershell
.\.venv\Scripts\python.exe setup_cpi_databases.py
```

This creates missing databases, initializes their tables and initial accounts,
and saves the CPI backend URL in its encrypted secret store. It does not copy
records from the original Credit_Dossier databases.

## 2. Start MCP — terminal 1

Start PostgreSQL first, then open PowerShell and run:

```powershell
cd "C:\Users\2863775\Documents\CRO_Solutions\credit policy intelligence\cd_cpi_server\credit_dossier_mcp"
..\credit_dossier_backend\.venv\Scripts\python.exe server.py
```

MCP endpoint: **http://127.0.0.1:8004/sse**.

## 3. Start backend — terminal 2

Open a separate PowerShell window and run:

```powershell
cd "C:\Users\2863775\Documents\CRO_Solutions\credit policy intelligence\cd_cpi_server\credit_dossier_backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8003
```

API documentation: **http://127.0.0.1:8003/docs**.

## 4. Start frontend — terminal 3

Open a separate PowerShell window and run:

```powershell
cd "C:\Users\2863775\Documents\CRO_Solutions\credit policy intelligence\cd_cpi_server\credit_dossier_frontend"
npm run dev
```

Open **http://localhost:8081**. The frontend already proxies API requests to port `8003`; no environment command is needed.

Keep all three terminals open. Press `Ctrl+C` in each terminal to stop its service.

## Manufacture Data

Sign in as a relationship manager or credit analyst and select **Manufacture Data**.
Enter the company name, industry, and geography, then start the job. The page displays
PDF generation, Mistral uploads, PostgreSQL table seeding, and the final result.

Both Python requirements files must be installed in the backend environment because
the backend uses that interpreter to launch the manufacturing process.

## Configuration

### Copy original Credit_Dossier data

From `credit_dossier_backend`, inspect the original and CPI databases:

```powershell
.\.venv\Scripts\python.exe copy_original_databases.py
```

To replace CPI data with verified copies of the original backend and MCP data:

```powershell
.\.venv\Scripts\python.exe copy_original_databases.py --copy
```

This reads the original databases without changing them, restores PostgreSQL
snapshots into staging databases, and verifies every table's contents and sequence
values before activating the copies. Previous CPI databases are retained with
`_before_<timestamp>` names. Dumps and verification reports are stored under
`credit_dossier_backend/.data/database_copies/`. CPI connections are briefly
disconnected during activation. User accounts and passwords come from the original
database after copying. Mistral library references retain their existing remote IDs.

The CPI backend uses `cpi_credit_dossier_backend`, and CPI MCP uses
`cpi_credit_dossier_mcp` on the local PostgreSQL server. These databases are
separate from the original Credit_Dossier databases. The backend `DATABASE_URL`
is stored in the copied backend's encrypted `.data` secret store; MCP's
`POSTGRES_DB` is configured in `credit_dossier_mcp/.env`. Mistral credentials
remain shared. Restart both CPI Python services after changing database settings.
Protected secrets must be used under the original Windows user or configured again
using the copied backend's secret-management scripts. The Python PostgreSQL driver
also requires the system PostgreSQL `libpq` library to be available.

These copies use frontend `8081`, backend `8003`, and MCP `8004`. The original
Credit_Dossier and Credit Policy Intelligence application files are unchanged.
