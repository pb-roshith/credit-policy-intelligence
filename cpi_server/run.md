# Run the Credit Policy Intelligence Platform

Requires Node.js 18+, Python 3.10+, and PostgreSQL.

Current project folder: `C:\Users\2863775\Documents\CRO_Solutions\credit policy intelligence\cpi_server`.
Ensure PostgreSQL is running before starting the backend.
This project uses frontend port `5173` and backend port `8002`, so it can run
alongside Credit_Dossier on ports `8080` and `8000`. The frontend API address
is saved in `frontend/.env.local`; no PowerShell environment command is needed.
If dependencies are already installed, use **Run after setup**; moving the folder
on this computer does not require reinstalling them.

## 1. First-time setup and run

Open PowerShell in the project folder and start the backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8002
```

Open a second PowerShell window in the project folder and start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

## 2. Run after setup

Open PowerShell in the project folder and start the backend:

```powershell
cd "C:\Users\2863775\Documents\CRO_Solutions\credit policy intelligence\cpi_server\backend"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8002
```

Open a second PowerShell window in the project folder and start the frontend:

```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173**.

API documentation: **http://localhost:8002/docs**

## Integrated policy extraction

Open **Policy Intelligence > Policy Rule Library**, select a policy and click
**Extract Rules**. The risk schema, taxonomy, ontology and NetworkX graph run in
the existing backend. There is no Risk Knowledge tab or technical stage panel.
The library shows **Completed** when extraction and quality review finish without
failures. Partial results retain their saved rules and show **Completed with errors**
with a retry action. Retry keeps the same job, skips successful policy documents,
and reuses source-validated batches while refreshing their vocabulary mappings.
Clause failures and unresolved mappings remain available in backend records.

Source-backed rules and eligible taxonomy/ontology items are approved
using the `system:auto-approval` actor, with audit history. Numeric source
validation is retained. Approved rules are available to compliance assessments automatically without
a separate activation step; the latest eligible version is used. Zero-result extraction
shows the failed stage or worker error with a retry action. Long-running AI calls
keep the job heartbeat active; model timeouts and temporary service errors receive
bounded retries. Automatically approved rules still receive advisory quality review.

After updating, run `backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`
from `cpi_server` once to install workbook/upload dependencies, then restart the
same backend/frontend processes. Migration `006_risk_knowledge.sql` is applied by
the existing database bootstrap. More details are in
[backend/docs/risk-knowledge/README.md](backend/docs/risk-knowledge/README.md).

## Default administrator

The administrator login and PostgreSQL connection are configured in
`backend/.env`. The local development defaults are `admin` / `Admin@123456`,
with PostgreSQL at `postgresql://postgres:root@localhost:5432/credit_policy_intelligence`.
On first startup, the backend creates the configured database and all required
schemas, tables, indexes, roles, and security policies when they are missing.
The PostgreSQL user in `DATABASE_URL` must have `CREATEDB` and `CREATEROLE`
permissions for initial setup. Existing data is not deleted on later starts.
Change both passwords before deploying or sharing the application.
