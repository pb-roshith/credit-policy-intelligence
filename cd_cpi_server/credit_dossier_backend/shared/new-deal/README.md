# Credit Dossier creation and CPI viewing

Credit Dossier is the only UI that creates deals. Its New Deal form contains
Customer Details and Facility Details; the Credit Policy Details section has
been removed. CPI's Credit Request Workbench is view-only, and its deal-creation
endpoints return 403 directing the user to Credit Dossier.

CPI retrieves current, role-authorized records through the persistent Mistral
Credit Dossier Deal Retrieval Agent. The agent can call only `list_owned_deals`,
which accepts no user ID or filters. The server binds the query to the verified
Dossier account: relationship managers receive their own deals, while credit
analysts receive all deals. It returns database records verbatim. The model cannot
rewrite deal values or grant access to another owner. CPI does not insert or
update deal records or compliance projections during retrieval. The existing
workbench table and AI Credit Assistant display retrieved deals using a read-only
UI mapping. Missing rating, exposure, coverage, pricing and compliance values
receive stable illustrative assumptions, identified in the assistant. Actual
Dossier fields and currencies take precedence. The assistant shows policy names
from the CPI catalogue, risk factors and recommended actions. Existing CPI rows
are retained; linked deal rows are deduplicated. INR and other
currencies are displayed as stored. Existing CPI policy data is preserved.

If the model is unavailable, the same authorized read query supplies current
records and the UI identifies that fallback. Retrieval runs on login/page entry,
on returning to the CPI tab/window, and through Refresh deals.

## Identity

Users can sign in to CPI using their Credit Dossier user ID and password.
Dossier verifies the password using the same password, approval and lockout
checks as its native login. CPI links or provisions a local identity mirror;
it never copies a password or its hash. A Dossier-only user does not need to
register separately in CPI. SKY resolves to the canonical Dossier user `sky`.

CPI creates its own HTTP-only session and CSRF cookies. Signing in to CPI does
not replace the user's Dossier session. Linked sessions recheck Dossier account
status and role. Locked, inactive, unapproved or role-changed source accounts
cannot keep accessing CPI. Password recovery for linked accounts takes place
in Dossier. CPI's separate administrator login and existing CPI-only accounts
are retained. A rejected Dossier password never falls back to a local password.

## APIs

- Dossier browser creation: `POST /api/deals`.
- CPI viewing: `GET /api/deals`, returning `{deals, status, source, ...}`.
- Server-only retrieval: `POST /api/shared/deals/retrieve`.
- Server-only authentication: `POST /api/shared/deals/identity/authenticate`.
- Server-only account check: `GET /api/shared/deals/identity`.

Server-only endpoints require `X-Shared-Deal-Key`. Retrieval also receives the
canonical login ID in `X-Shared-User-Id`. These credentials remain in the backends.
Agent configuration is persisted in `shared_deal_agents`, independent of the
Dossier section-agent cleanup lifecycle. Mistral retrieval conversations contain
deal IDs and counts, while full records come directly from PostgreSQL.

## Run

Both local backend .env files already contain a matching random
`SHARED_DEAL_API_KEY`, excluded from Git. CPI points `SHARED_DEAL_API_URL` at
`http://127.0.0.1:8003`. This copied Dossier backend currently uses the same
Dossier database as the original app, so original Dossier deals are visible.
For other environments, point the shared API at the backend serving the intended
Dossier database, inject the shared key through the secret store, and use HTTPS
between hosts. Dossier's Mistral API key remains in its existing secret provider.

From `cd_cpi_server/credit_dossier_backend`:

```powershell
.\.venv\Scripts\python.exe scripts/provision_new_deal_agent.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8003
```

From `backend`, in another terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8002
```

Run `npm run dev` in each frontend folder. CPI uses 5173; copied Dossier uses
8081. Restart running backends to load authentication and retrieval changes.
Sign in to CPI with the Dossier credentials and open Credit Requests. Keep the
repository layout intact for frontend builds; both use the shared summary.

## Verification

In each backend, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_shared_deals.py -v
```

From the Dossier backend, run:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_shared_deal.py --user SKY
.\.venv\Scripts\python.exe scripts/smoke_dossier_identity.py
```

The first test uses live HTTP and the hosted agent to compare a user's actual
Dossier records against the returned canonical IDs without changing them.
The second uses a synthetic Dossier-only account to test password verification,
CPI identity provisioning, CPI sessions, live agent retrieval and the read-only
creation restriction. All synthetic database records are rolled back; Mistral
retains the test retrieval conversations. SKY's two existing deals were retrieved
successfully, and the Dossier-only login integration test passed locally.

Both frontend production builds pass. The full Dossier TypeScript check has two
existing narrowing errors in `src/routes/observability.tsx` (1202 and 1206).
Document manufacturing and cross-app document-library reuse are deferred.
