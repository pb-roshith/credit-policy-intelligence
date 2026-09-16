# Backend

Run with `uvicorn main:app --reload --port 8000` from this directory. API docs are available at `/docs`.

Set `DATABASE_URL` in `.env` to the desired PostgreSQL database. On first startup,
the backend connects to the `postgres` maintenance database and creates the
configured database when it is missing. The configured PostgreSQL role therefore
needs `CREATEDB` permission for the first run; later runs only require normal
access to the application database.

The backend is organized by responsibility:

- `main.py` creates the FastAPI application and registers routers.
- `app/routers/` contains authentication, request, compliance, policy, control, exception, and decision endpoints.
- `app/manufacture_data/` contains separate routers for credit-request, exposure-history, policy-control, and policy-PDF generation.
- `app/services/` contains reusable compliance scoring and AI review logic.
- `app/scripts/` contains administrative commands that are run with `python -m`.
- `app/database.py`, `app/security.py`, `app/schemas.py`, and `app/config.py` contain shared infrastructure.

Borrowers are stored in `credit_data.borrower` with a stable `borrower_id` and a unique trimmed, case-insensitive name. Request creation accepts an optional `borrower_id`; when supplied, its name must match. Otherwise the name resolves or creates the borrower. Request responses include the borrower ID.

Credit request numbers are unique in `credit_requests`. Exposure history uses borrower ID, facility reference, and reporting month; it no longer stores credit request numbers. Repeated generation updates matching monthly records. Exposure calculations sum the latest balance for each facility, including zero balances for repaid facilities.

`migrations/001_borrower_reset.sql` is a destructive, one-time reset for the previous local schema, applied on 2026-09-10 at the user's request. It clears borrower, request, exposure, financial-history, compliance, and policy-evaluation records. Do not rerun it to start the application. Startup does not seed demo borrowers.

Set `MISTRAL_API_KEY` in `backend/.env` for server-side use. The environment file is ignored by Git.

Policy PDF manufacturing runs as a sequential background job in the shared `credit_data` policy store. It creates or reuses one Mistral Library and one Mistral Agent, generates 25 synthetic PDFs, and imports the 10 DOCX files from `backend/policy doc`. All 35 files are uploaded, indexed, and summarized in the same library. Generated PDF filenames use the policy title without the clause-number prefix; clause numbers remain in the document and catalog metadata. Completed documents are reconciled and reused on later runs.

The 25 PDFs are organized by policy type and category. `Credit Policy` contains the wholesale, retail, and rating standards; the set also covers collateral, pricing, sector, delegation, regulatory capital, currency, duration, liquidity, and risk-appetite policies. The hierarchy is persisted with each document through `policy_category`, `parent_policy`, `clause_number`, and `display_order`.

Existing DOCX policies can also be imported idempotently with `python -m app.scripts.import_external_policies <directory>`. The configured POL-71 through POL-80 set is stored under `Special Assets & Recovery` > `Problem Credit Management`, uploaded to the same Mistral Library, summarized once, and marked with `source_type = 'imported'`. The normal Policy PDF manufacturing action includes these 10 documents in its 35-file completion count.

The Policy Library uses one collapsible Policy Types tree. Its taxonomy covers Leverage, Collateral, Pricing, Tenor, Covenant, Sector, Delegation, Rating, Country, Industry, LTV, DSCR, Concentration, Currency, Duration, Liquidity, Underwriting, Risk Appetite, Regulatory Capital, and Special Assets & Recovery. The former `ensure_policy_types` maintenance command remains idempotent, while its five policy definitions are now included directly in the standard 25-PDF manufacturing workflow.

Policy controls are stored in `credit_data.policy_controls`. Use **Data Manufacturing > Generate Policy Controls** to create between one and five controls for every policy document. The authenticated `GET /api/controls` endpoint supplies the dynamic Controls Register, including policy ID, policy number, policy name, control identity, owner, clause, type, automation, frequency, effectiveness, status, testing data, and assessment.

Every document also has a stable Policy Library ID in `policy_documents.library_policy_id`. IDs follow the visible tree: policy type 1 contains `1.1`, `1.2`, and so on. Controls keep a foreign key to the document's database primary key, while the API joins back to `policy_documents` to return the matching Library ID. Control status is restricted to `Effective`, `Needs Improvement`, or `Ineffective`; descriptions and manufactured assessments are stored per control.

Policy-to-policy mappings are stored as symmetric pairs in `credit_data.policy_relationships`. Run `python -m app.scripts.map_policy_relationships` after adding or reclassifying documents. The mapper relates documents by policy family, policy type, policy category, and explicitly associated risk domains. `GET /api/policies/{policy_id}/relationships` returns the related documents from either side of a stored pair.

Policy Copilot uses the configured Mistral agent and its attached document library for retrieval-grounded chat. `POST /api/policy-copilot/chat` starts a stored Mistral conversation or appends to the supplied conversation ID, returning an answer and citations mapped to Policy Library IDs. The selected-policy controls endpoint is `GET /api/policies/{policy_id}/controls`.
# User data isolation

All account credit data is stored in the single PostgreSQL schema `"user"`.
Every table includes `user_id`; primary keys, unique indexes, and foreign keys
include ownership so existing request numbers and borrower IDs are preserved.
Authenticated connections set the canonical user ID for the transaction and use
the restricted `credit_user_runtime` role. PostgreSQL row-level security enforces
account isolation for reads and writes, including administrator accounts.

Policy Intelligence remains shared in `credit_data`. Authentication and
administration tables remain in `public`. Preserved historical account-local
policy tables in `"user"` are archival; policy APIs use the shared catalog.

The backend runs the idempotent migration at startup. To run it explicitly:
`python -m app.user_store` from `backend`. PostgreSQL 15 or newer is required.
The migration database role needs schema/table creation and role-management
permissions. Stop older backend processes before migration and start the updated
backend afterward; older code must not continue writing to account schemas.

Migration copies all tables from each known `user_<hash>` schema, retains IDs,
verifies all copied column values in both directions, validates foreign keys,
and removes the old schemas in one transaction. Unknown owners or unexpected
tables abort the migration. Existing unowned credit data from `credit_data` is
also preserved under the reserved owner `__legacy_unassigned__`; its original
copy remains in `credit_data` and is not exposed to signed-in accounts.

For account-specific maintenance, set `app.database.account_user_id` to the
canonical user ID before calling `db_connection()` and reset the context token
when finished. Shared policy maintenance uses `shared_policy_connection()`.
Run `python -m unittest discover -s tests -v` for integration checks; cleanup
removes only rows owned by randomly named test accounts.
