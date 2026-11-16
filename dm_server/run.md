# Data Manufacturing server

Open **http://localhost:5174**. API: **http://localhost:8005**.

Sign in with the same approved account used by CPI and Credit Dossier. Login styling, registration, password recovery, account approvals and security rules use the existing shared implementation. DM has separate `dm_session` / `dm_csrf` cookies and application-scoped session rows: signing in/out of DM does not terminate a CPI session.

DM owns the Data Manufacturing page and exposes credit-request, borrower-exposure-history, exception, policy-control and policy-document generation. CPI retains its other pages and the generated-data registers. Generation writes to the same account-protected data store used by CPI; no data migration or duplication is needed. Control generation remains additive.

## Start with the other applications

From the workspace root, run `start_all.bat`. It now opens seven server tabs, including the two DM processes. `stop_all.bat` recognizes the DM ports too.

## Initial setup

Use the existing CPI Python environment, which already contains the shared service dependencies. Alternatively create a dedicated DM environment:

```powershell
cd dm_server/backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Install the frontend dependencies:

```powershell
cd dm_server/frontend
npm ci
```

## Start individually

Backend (from `dm_server/backend`, using the existing CPI environment):

```powershell
../../cpi_server/backend/.venv/Scripts/python.exe -m uvicorn main:app --reload --reload-dir . --reload-dir ../../cpi_server/backend/app --host 127.0.0.1 --port 8005
```

Frontend (from `dm_server/frontend`):

```powershell
npm run dev
```

Database, identity and AI settings are shared from `cpi_server/backend/.env`. This avoids duplicating credentials. An optional `DM_CORS_ORIGINS` environment override controls DM origins. Frontend overrides are documented in `frontend/.env.example`; the defaults are API 8005 and CPI 5173.

The shared CPI backend services and frontend login/style components remain common libraries. Both application folders must remain siblings in this workspace. DM does not mount CPI assessment, graph or portfolio routes. CPI no longer mounts the `/api/data-manufacturing` routes or displays the Data Manufacturing page.

The View Credit Requests, View Exceptions, View Controls Register and View Policy Library actions open the appropriate CPI page in a new tab. CPI login remains independent.

## Verification

```powershell
# From dm_server/backend
../../cpi_server/backend/.venv/Scripts/python.exe -m unittest discover -s tests -v
# From dm_server/frontend
node --test tests/*.test.mjs
npm run build
```
