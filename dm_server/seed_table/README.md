# Static deployment snapshots

`cpi.dump`, `dossier.dump`, and `mcp.dump` contain the schemas, tables, and
data for the three application databases. They contain private application data,
including user account records. Keep the directory on private deployment storage.
Git ignores the dumps and the legacy recovery copies under `history/`.

Configure this command as a one-time pre-start or release step from the workspace
root, using the Python environment installed for CPI or Data Manufacturing.

```powershell
python dm_server/backend/deployment_seed.py restore
```

Provide `CPI_SEED_DATABASE_URL`, `DOSSIER_SEED_DATABASE_URL`, and
`MCP_SEED_DATABASE_URL` for three provisioned, empty PostgreSQL 18 databases.
Use deployment credentials with schema creation permissions, and create the
server-level `credit_user_runtime` role for CPI before running the command. The
restore uses target ownership and privileges. Apply your deployment's runtime
role grants separately. Use PostgreSQL client tools on `PATH` and include
[`seed_others`](../seed_others/README.md) on the deployed filesystem.

The command restores each database transactionally, records the dump checksum,
and skips databases already restored from the same dump. It rejects populated
targets. Use `--database cpi`, `--database dossier`, or `--database mcp` to restore
a single target. Run CPI's [database setup step](../../run.md#installation-and-runtime-permissions)
after the restore to apply any schema changes before starting the services.

For Gemini, set `GEMINI_STORE_PATH` to the persistent, shared runtime file for
MCP and the Dossier backend. The restore initializes it from the bundled SQLite
snapshot if it is missing. For a deployment using Mistral, the existing remote
document IDs require the original provider account. Supply any database record
decryption keys through deployment secrets, separately from the dumps.

To deliberately refresh the static PostgreSQL dumps, point the same variables at
the source databases and run the command with `snapshot`. Capture the matching
files and Gemini store again if they changed. There is no scheduled refresh.
