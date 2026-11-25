# Static deployment snapshots

`cpi.dump`, `dossier.dump`, and `mcp.dump` contain the schemas, tables, and
data for the three application databases. They contain private application data,
including user account records. Keep the directory on private deployment storage.
Git ignores the dumps and the legacy recovery copies under `history/`.

Fill in `dm_server/backend/.env` using `dm_server/backend/.env.example` and start the services
normally. Each service automatically restores its configured snapshot before
initializing its database. CPI and Data Manufacturing share the CPI target.

Provide `CPI_SEED_DATABASE_URL`, `DOSSIER_SEED_DATABASE_URL`, and
`MCP_SEED_DATABASE_URL` as `postgresql://` URLs for three provisioned, empty
PostgreSQL 18 databases. Use roles with permission to restore the schemas,
provision the server-level `credit_user_runtime` role for CPI, and have
PostgreSQL client tools on `PATH`. Deploy both this directory and
[`seed_others`](../seed_others/README.md). The `.env` file is ignored by Git.

Process environment variables can override the seed URLs. The services use these
same URLs by default. If separate runtime credentials are injected through the
normal service settings, point them at the same databases and grant them the
required runtime permissions. CPI's production runtime role must still meet its
existing least-privilege checks.

Restores are transactional and recorded by checksum. Normal startup skips already
populated application databases. A blank URL disables automatic restore for that
service. A database containing unrelated tables is rejected.

For Gemini, set `GEMINI_STORE_PATH` to the persistent, shared runtime file for
MCP and the Dossier backend. The restore initializes it from the bundled SQLite
snapshot if it is missing. For a deployment using Mistral, the existing remote
document IDs require the original provider account. Supply any database record
decryption keys through deployment secrets, separately from the dumps.

To deliberately refresh the static PostgreSQL dumps, point the same variables at
the source databases and run `python dm_server/backend/deployment_seed.py snapshot`. Capture the matching
files and Gemini store again if they changed. There is no scheduled refresh.
