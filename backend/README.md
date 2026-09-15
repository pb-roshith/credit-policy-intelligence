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

Authenticated API calls use a separate PostgreSQL schema for each canonical user ID for credit requests, borrowers, exposure history, compliance results, and AI reviews. Policy Intelligence is shared through `credit_data`, including policy documents, controls, relationships, generation jobs, and AI library/agent configuration. Authentication and administration tables remain in `public`.

Schemas are initialized automatically on first authenticated use. Request numbers and borrower IDs are local to each account. Policy generation writes to the common `generated_policies` directory and every authenticated role reads the same Policy Intelligence library.

Existing policy records in `credit_data` are the shared Policy Intelligence catalog. Legacy credit-request records there remain outside user accounts because their ownership cannot be established. Account-specific credit-data maintenance must explicitly set `app.database.data_schema` to `user_schema(canonical_user_id)` before opening connections.

Restart the backend to activate this change. Run isolation integration checks with `python -m unittest discover -s tests -v` from `backend`; these use and remove randomly named test-user schemas in the configured database.
