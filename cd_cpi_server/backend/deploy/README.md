# Production data protection

Apply this profile to the `cd_cpi_server` intranet deployment. The localhost development profile remains available for development data.

| Classification | Data | Protection |
| --- | --- | --- |
| Restricted authentication data | Passwords, recovery answers, and session tokens | Unique salted PBKDF2-HMAC-SHA256 for passwords and recovery answers. SHA-256 for random session tokens. Secure, HttpOnly browser session cookie over HTTPS. |
| Restricted service secrets | Database credentials, provider API keys, and report masking key | Inject from the deployment secret manager. Production rejects populated secret entries in service `.env` files. Restrict service and certificate private keys to their service accounts. |
| Confidential credit data | Dossiers, documents, extracted text, narrative versions, exports, and company data | Encrypted database and filesystem storage. TLS on network connections. Application access checks and existing export masking for recognized email addresses, PAN, Aadhaar, labeled account numbers, and phone numbers. Reports may still contain confidential business information. |
| Restricted audit and diagnostics | Audit identifiers, source IPs, customer names, and operational logs | Encrypted database and log storage. Administrator-only access to the application audit trail. SQL parameter logging is suppressed and production Mistral telemetry is disabled. |
| Internal | Static UI and routine service configuration without secrets | HTTPS from the browser. Store service configuration with restricted host access. |

## Transport and secrets

1. Configure the gateway from [`nginx.conf.example`](nginx.conf.example) with certificates trusted by the intranet clients and backend. Leave the backend, MCP, and frontend runtime listeners on `127.0.0.1`. Give the frontend SSR runtime the built frontend artifacts on port `8081`. Publish only TCP `443` from the application host. The unencrypted upstream hops in this configuration stay on the same trusted host. If services are moved to separate hosts, configure verified TLS for those upstream hops as well.
2. Set `APP_ENV=production`, `CORS_ALLOWED_ORIGINS=https://<intranet-host>`, `MCP_SSE_URL=https://127.0.0.1:8444/sse`, `MCP_HOST=127.0.0.1`, and `REPORT_MASK_SENSITIVE_DATA=true`. Set `SSL_CERT_FILE` to a CA bundle containing the MCP issuer and the public roots needed by other outbound HTTP clients. Install the intranet certificate chain on the gateway and client trust stores. Use `nginx -t` before starting or reloading the gateway.
3. Inject `DATABASE_URL` for the backend, `MCP_DATABASE_URL` for MCP and its data tools, a persistent `REPORT_TOKENIZATION_KEY` (URL-safe base64 of at least 32 random bytes), and the required provider and integration credentials. Remove populated secrets from both service `.env` files before startup and rotate any production credentials previously stored there.
4. Provision both PostgreSQL databases with TLS 1.2 or later, a certificate for the DNS name in each connection string, and a trusted CA via `sslrootcert` or `PGSSLROOTCERT`. Configure `hostssl` rules for the application roles. The production clients require verified certificates and refuse connections that do not negotiate TLS 1.2 or TLS 1.3.
5. Start the API from `backend` with `python -m uvicorn app.main:app --host 127.0.0.1 --port 8003 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log`. The gateway overwrites forwarded headers, and the API rejects requests that arrive without HTTPS as the original scheme. Run the MCP service with its usual `python server.py` entry point.

## Encrypted storage and deployment evidence

Provision encrypted storage before loading any production data. Existing data, temporary uploads, logs, and backups need the same protection as newly written records.

- On the application host, cover `UPLOAD_DIR`, the dossier package and generated document directories, the local AI data store if enabled, service and gateway log directories, and process temporary directories. Include PostgreSQL data/WAL, tablespaces, logs, dumps, and backups on database hosts. Include the actual storage targets of mounted paths and archived logs.
- On Windows, run PowerShell with permission to read BitLocker status and check the actual paths using `./Test-EncryptedStorage.ps1 -StoragePath <paths>`. It fails if any supplied path cannot be verified or its volume is not fully encrypted with protection on. On a managed service, collect equivalent encryption and key-management evidence for databases, snapshots, and backup storage.
- Validate the deployed browser endpoint and internal MCP endpoint with TLS 1.2 or 1.3 and verify that older protocols fail. Confirm the two PostgreSQL sessions report TLS in `pg_stat_ssl`. Verify an approved user can sign in, retrieve a dossier, and download a report with test identifiers masked. Retain encryption and TLS evidence for the IP Safe submission. For cloud AI or storage used by the deployment, confirm provider-side encryption and authorization for the data classification before sending live data.
