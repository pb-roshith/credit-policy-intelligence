# Run Credit Dossier, Credit Policy Intelligence, and Data Manufacturing

## Start and stop all applications

Start PostgreSQL, then double-click `start_all.bat` in this folder. It opens
one Windows Terminal window with seven named Command Prompt tabs using the existing
Python environments and Node dependencies. Windows Terminal is required.
Keep the tabs open while using the applications. Double-click `stop_all.bat` to
stop all seven servers together, or press Ctrl+C in a tab to stop one server.
The self-contained `stop_all.bat` identifies this project's processes
on the seven server ports and stops their child processes too. Server tabs remain
open and can be closed afterward. PostgreSQL stays running.
If a port is already occupied, stop its existing server before starting again.

| Server | Port |
| --- | --- |
| Credit Dossier MCP | 8004 |
| Credit Dossier backend | 8003 |
| Credit Dossier frontend | 8081 |
| Credit Policy Intelligence backend | 8002 |
| Credit Policy Intelligence frontend | 5173 |
| Data Manufacturing backend | 8005 |
| Data Manufacturing frontend | 5174 |

| Application | Browser URL |
| --- | --- |
| Credit Dossier | http://localhost:8081 |
| Credit Policy Intelligence (CPI) | http://localhost:5173 |
| Data Manufacturing (DM) | http://localhost:5174 |

## First-time setup

Use Python 3.10+, Node.js 20.19+ in the 20 series or 22.12+ in the 22 series or later, and PostgreSQL. Windows Terminal is required for the combined launcher. Run the following from the workspace root in PowerShell.

```powershell
Push-Location cd_cpi_server/backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r ../mcp/requirements.txt
Pop-Location

Push-Location cpi_server/backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Pop-Location

npm --prefix cd_cpi_server/frontend ci
npm --prefix cpi_server/frontend ci
npm --prefix dm_server/frontend ci
```

Configure local settings in the Dossier backend, Dossier MCP and CPI backend using their `.env.example` files. Keep the server folders together so they can load shared code. Start PostgreSQL and complete [Dossier database provisioning](#provision-the-dossier-databases) when setting up a fresh local installation.

DM can use the CPI Python environment. To give DM its own environment, run the following from the workspace root. The combined launcher uses it when present.

```powershell
Push-Location dm_server/backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Pop-Location
```

## Start services individually

Start PostgreSQL first. In a separate PowerShell terminal for each service, start from the workspace root and change to the directory in the table before running the command. Press Ctrl+C in that terminal to stop the service.

| Service | Directory | Command |
| --- | --- | --- |
| Dossier MCP | `cd_cpi_server/mcp` | `../backend/.venv/Scripts/python.exe server.py` |
| Dossier backend | `cd_cpi_server/backend` | `./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8003` |
| Dossier frontend | `cd_cpi_server/frontend` | `npm run dev` |
| CPI backend | `cpi_server/backend` | `./.venv/Scripts/python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8002` |
| CPI frontend | `cpi_server/frontend` | `npm run dev` |
| DM backend | `dm_server/backend` | `../../cpi_server/backend/.venv/Scripts/python.exe -m uvicorn main:app --reload --reload-dir . --reload-dir ../../cpi_server/backend/app --host 127.0.0.1 --port 8005` |
| DM frontend | `dm_server/frontend` | `npm run dev` |

If you created a dedicated DM environment, use `./.venv/Scripts/python.exe` in the DM backend command. Local API docs are at http://127.0.0.1:8003/docs for Dossier and http://127.0.0.1:8002/docs for CPI. Dossier MCP listens at http://127.0.0.1:8004/sse.

## Shared AI provider

CPI, Dossier and Dossier MCP use the shared provider at `cd_cpi_server/backend/ai_runtime.py`. From that backend directory, run its tests with `./.venv/Scripts/python.exe -m unittest discover -s tests -p test_ai_runtime.py`.

AI generation supports `AI_PROVIDER=gemini` or `AI_PROVIDER=mistral`. Set the
same provider in the CPI backend, Dossier backend, and Dossier MCP `.env` files.
Gemini uses `GEMINI_API_KEY` and `GEMINI_MODEL=gemini-3.5-flash-lite` through
the official `google-genai` Python SDK. Install each service's requirements
after updating, then restart all three Python services. `.env.example` contains
placeholders; keep real keys in the ignored `.env` files.

Temporary Gemini capacity failures (including HTTP 503) use the SDK's bounded
retry policy: six total attempts, with exponential backoff starting at two
seconds and capped at sixteen seconds, plus jitter. Each Python server process
allows at most two simultaneous Gemini requests, including retries. Persistent
provider overload still requires trying again later; the configured model is
preserved.

Gemini agent definitions, conversations, and source documents are stored in
the ignored `.ai-data/gemini.sqlite3` file at the repository root. Both backends
and MCP must share this file; `GEMINI_STORE_PATH` can override its location.
Back it up with the application data. Gemini receives the attached documents
as context; it does not use Mistral's hosted retrieval or Observability judges.
CPI restores its policy library from local PDFs on first use. For Dossier,
re-manufacture the company data pack and re-sync existing deals after switching
providers; re-upload documents stored only in the previous provider. Keep the
original Mistral key configured if you plan to switch back later.

## Credit Dossier

For intranet deployment, use the [production data protection configuration](cd_cpi_server/backend/deploy/README.md).
The commands below are for local development.

The administrator dashboard lists recent security and operational alerts. An
alert is raised when an account is locked or when, within ten minutes, the API sees
five failed sign-ins from one source, three administrator access denials for one
account, or five server errors. Repeated alerts of the same type and scope are
suppressed for ten minutes. Alert records remain in the audit trail, and the
application logs the alert code and event ID for monitoring. The dashboard loads
alerts when opened and provides a refresh button. External notification delivery
requires a deployment monitoring integration.

### Provision the Dossier databases

To provision the isolated Dossier databases with the configured local PostgreSQL
credentials, run from `backend`:

```powershell
.\.venv\Scripts\python.exe setup_cpi_databases.py
```

This creates missing databases, initializes their tables and initial accounts,
and saves the CPI backend URL in its encrypted secret store. It does not copy
records from the original Credit_Dossier databases.

### Manufacture Data

Sign in as a relationship manager or credit analyst and select **Manufacture Data**.
Enter the company name, industry, and geography, then start the job. The page displays
PDF generation, Mistral uploads, PostgreSQL table seeding, and the final result.

Both Python requirements files must be installed in the backend environment because
the backend uses that interpreter to launch the manufacturing process.

### Copy original Credit_Dossier data

From `backend`, inspect the original and CPI databases:

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
`backend/.data/database_copies/`. CPI connections are briefly
disconnected during activation. User accounts and passwords come from the original
database after copying. Mistral library references retain their existing remote IDs.

The CPI backend uses `cpi_credit_dossier_backend`, and CPI MCP uses
`cpi_credit_dossier_mcp` on the local PostgreSQL server. These databases are
separate from the original Credit_Dossier databases. The backend `DATABASE_URL`
is stored in the copied backend's encrypted `.data` secret store; MCP's
`POSTGRES_DB` is configured in `mcp/.env`. Mistral credentials
remain shared. Restart both CPI Python services after changing database settings.
Protected secrets must be used under the original Windows user or configured again
using the copied backend's secret-management scripts. The Python PostgreSQL driver
also requires the system PostgreSQL `libpq` library to be available.

These copies use frontend `8081`, backend `8003`, and MCP `8004`. The original
Credit_Dossier and Credit Policy Intelligence application files are unchanged.
### Loading the company list and documents on a fresh deployment

The MCP automatically imports the company list and original documents from
[`backend/dossier_data`](cd_cpi_server/backend/dossier_data/README.md).
Include that entire folder on the MCP service. It contains only company catalog
metadata and original document files. Company access retains its existing owner
username. See its README for Neon configuration and import behavior.

## Credit Policy Intelligence

For local HTTP development, set `APP_ENV=development` in `backend/.env`
and configure a local administrator password. Process environment variables
take precedence over that file.

### Production operational controls

Set `APP_ENV=production` and provide a unique administrator password and
the shared identity API key through deployment secrets. Terminate HTTPS at the
ingress, set `SESSION_COOKIE_SECURE=true` and `ENABLE_HSTS=true`, and set
`CORS_ORIGINS` to the exact HTTPS frontend origins. Use HTTPS for the shared
identity API when it runs on a separate host. Loopback HTTP is supported for
a service on the same host. CPI validates these settings before initializing
the database and serves interactive API documentation only in development.

Use a deployment secret store with encryption at rest for `DATABASE_URL`,
`ADMIN_PASSWORD`, `SHARED_DEAL_API_KEY`, and the configured AI provider key.
Inject each secret as an environment variable or use its `_FILE` setting to
point to a read-only mounted secret outside the application directory.
Production ignores these secret settings from `backend/.env`.

Serve the frontend over HTTPS and route its API calls to an HTTPS endpoint.
Set `VITE_API_URL` for a separate HTTPS API origin or route `/api` through the
frontend's HTTPS origin. Production rejects requests that reach the API as
HTTP. When TLS terminates at ingress, configure it to set
`X-Forwarded-Proto` from the incoming connection and configure Uvicorn to trust
forwarded headers only from the ingress addresses. Keep the backend port
private and route health checks through HTTPS.

Place a web application firewall at the public ingress. Apply managed web
attack rules and source-based limits to the authentication routes. Use
network firewall rules so only the ingress can reach the backend and only
authorized services can reach PostgreSQL. Verify these rules in the target
environment before recording the infrastructure controls as implemented.

Configure the frontend and API ingress to offer TLS 1.2 and 1.3 only. For
production PostgreSQL, set `sslmode=verify-full`,
`ssl_min_protocol_version=TLSv1.2`, and `gssencmode=disable` in
`DATABASE_URL`. Configure the trusted CA and use the database hostname on
its certificate. Outbound HTTPS to the shared identity service also uses
TLS 1.2 or newer with certificate verification.

Forward the CPI backend logs to the deployment's monitoring system and match
`CPI_SECURITY_ALERT` to route warnings to the operations team. Within a
60-second observation window, CPI warns on five rejected sign-in or password
reset requests, five access denials, or three rate-limit violations from one
source IP. It also warns on five server failures across sources. Counts are
local to each backend process.

See the [Error code book](cpi_server/docs/error-code-book.md) for logged codes and operator actions.

Optional AI graph fallback and automatic knowledge export are off by default.
Enable them explicitly with `POLICY_GRAPH_LLM_FALLBACK=true` or
`POLICY_KNOWLEDGE_AUTO_EXPORT=true` when needed.

Inject `DATA_ENCRYPTION_KEY` from the production secret store, or inject
`DATA_ENCRYPTION_KEY_FILE` with the path to a read-only mounted secret outside
the application directory. Grant access to the service identity. Production
ignores these key settings from `backend/.env`. Generate a
Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
in a secure administrative session. Use the same key across backend instances
and retain it for restores. New canonical credit records and AI trace inputs,
outputs, and error messages are encrypted with AES-256-GCM before PostgreSQL
writes. Older plaintext and Fernet-encrypted values remain readable. Keep PostgreSQL volumes and backups
encrypted to cover existing rows and other application tables.

See the [Data protection design and approval record](cpi_server/docs/data-protection-design.md)
for the protection decisions and sign-off evidence.

### Integrated policy extraction

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
[backend/docs/risk-knowledge/README.md](cpi_server/backend/docs/risk-knowledge/README.md).

### Installation and runtime permissions

Install Python packages into the project virtual environment and run the
service under a dedicated OS identity. Production startup rejects root on
Unix and an elevated administrator token on Windows. Use `backend/.env` for local
development credentials. An administrator password must be configured.

In production, run `python -c "from app.database import initialize_database; initialize_database()"`
from the backend directory as a separate deployment step with database
bootstrap credentials. Provision the database and roles first when the
database platform handles those resources. Then grant the service database
role only the application object access it needs, including membership in
`credit_user_runtime` for account-scoped operations, and inject that role's
connection string into the running service. Production startup skips
bootstrap and rejects PostgreSQL administration privileges. Repeat the
separate bootstrap step when deploying schema changes.

After production database bootstrap, import bundled policy knowledge and
build policy relationships before starting the API. Run this again when the
policy catalog changes. Local development still prepares the policy catalog
at startup.

```powershell
python -c "from app.services.policy_knowledge_package import autoload_package; from app.scripts.map_policy_relationships import map_policy_relationships; autoload_package(); map_policy_relationships()"
```

#### Component and operation privileges

| Component or operation | Required access |
|---|---|
| Frontend delivery | Read access to the built static files. Browser users access protected records through the authenticated API. |
| Backend service | Read deployed code, configuration, and mounted secrets. Grant write access only to directories used for uploads, generated outputs, and enabled knowledge exports. |
| Database bootstrap | Schema, object, and role administration required by the installation or migration. Run separately using the deployment identity. |
| Database runtime | Connect to the application database and grant access to the application objects used by the service. Grant membership in `credit_user_runtime` for account-scoped work. Production startup rejects PostgreSQL superuser, database creation, role creation, and replication privileges. |
| Account-scoped data | Executes under `credit_user_runtime` with PostgreSQL row-level security. An analyst's delegated access to canonical credit data is read-only. |
| Shared policy and authorized cross-account workflows | The backend checks the user role and operation before using its service database connection. Grant that connection only the shared and cross-account object access these workflows require. |
| Account administration | Administrator permission is required for account approval and unlock, password policy changes, and audit log access. |
| Exception workflow | Relationship managers can create exceptions and manage their own. Credit analysts can approve and manage authorized exceptions. |
| External integrations | The backend service identity reads the shared API credential and the configured AI provider credential. Apply access controls for each credential in the deployment secret store. |

Validate the actual OS permissions, service identity, database grants, and
secret access in the target environment. The table describes application
access requirements. Effective infrastructure privileges depend on deployment.

#### Privileged account management

This policy covers application administrators, PostgreSQL installation roles,
and infrastructure superusers for Credit Policy Intelligence. The application
owner and security owner must approve the policy before it is adopted.

- Grant privileged access to named custodians after the application or
  infrastructure owner approves the business need. Record the approver,
  permitted scope, custodian, and expiry where applicable.
- Use the dedicated, non-administrative service identity for routine operation.
  Use PostgreSQL installation privileges only during authorized installation
  or migration, and revoke temporary access when the work ends.
- Keep administrative credentials in the approved deployment secret store.
  Use named, individually logged vault access for the built-in administrator
  credential and change it when a custodian leaves or exposure is suspected.
- Review privileged access on the organization's approved schedule and after
  role changes. Revoke access promptly when it is no longer required.
- For emergency use, record the incident, custodian, reason, and actions.
  Review the use afterward and rotate exposed credentials. Retain the access
  approvals and audit records under the organization's retention policy.

For each periodic review, the application and infrastructure owners should
reconcile application administrator custodians, database administrator roles,
and infrastructure superusers against current access approvals. Include vault
access to the built-in administrator credential. Record each decision to
retain, reduce, or revoke access, link any remediation ticket, and track it
through closure. Keep completed reviews in the approved access-review system.

| Review date | Reviewer | Account or custodian | System and privileges | Decision and evidence | Next review due |
|---|---|---|---|---|---|

## Data Manufacturing

Open **http://localhost:5174**. API: **http://localhost:8005**.

Sign in with the same approved account used by CPI and Credit Dossier. Login styling, registration, password recovery, account approvals and security rules use the existing shared implementation. DM has separate `dm_session` / `dm_csrf` cookies and application-scoped session rows: signing in/out of DM does not terminate a CPI session.

DM owns the Data Manufacturing page and exposes credit-request, borrower-exposure-history, exception, policy-control and policy-document generation. CPI retains its other pages and the generated-data registers. Generation writes to the same account-protected data store used by CPI; no data migration or duplication is needed. Control generation remains additive.

Database, identity and AI settings are shared from `cpi_server/backend/.env`. This avoids duplicating credentials. An optional `DM_CORS_ORIGINS` environment override controls DM origins. Frontend overrides are documented in `dm_server/frontend/.env.example`; the defaults are API 8005 and CPI 5173.

The shared CPI backend services and frontend login/style components remain common libraries. Both application folders must remain siblings in this workspace. DM does not mount CPI assessment, graph or portfolio routes. CPI no longer mounts the `/api/data-manufacturing` routes or displays the Data Manufacturing page.

The View Credit Requests, View Exceptions, View Controls Register and View Policy Library actions open the appropriate CPI page in a new tab. CPI login remains independent.

### Verification

```powershell
# From dm_server/backend
../../cpi_server/backend/.venv/Scripts/python.exe -m unittest discover -s tests -v
# From dm_server/frontend
node --test tests/*.test.mjs
npm run build
```
