# Data protection design and approval

This design covers the Credit Policy Intelligence submission (`cpi_server`). The shared identity service, hosting infrastructure, and backup platform provide dependent controls. Approval status is **pending**.

## Current controls

| Data | Protection | Rationale |
|---|---|---|
| Canonical credit records and AI trace inputs, outputs, and error messages | New writes use AES-256-GCM with a fresh nonce and a key derived from the deployment secret. Legacy Fernet records remain readable. | Authorized features need to recover the original values. |
| Session and CSRF tokens | PostgreSQL stores hashes of randomly generated tokens. | The server can verify the presented token using its hash. |
| User passwords and recovery answers | The shared identity service stores salted hashes. | The identity service verifies the supplied values without recovering the originals. |
| Dashboard and AI telemetry exports | Server-side authorization, export audit events, and minimized reports. Telemetry exports omit raw trace payloads. | Reports expose the fields needed for their purpose. |
| Existing plaintext rows, other database tables, and backups | Deployment-level encryption and access controls require verification. | These stores include data outside the application-layer encryption coverage. |

This release uses encryption, hashing, and field omission. Assess masking before granting new audiences access to partial values. Assess tokenization before introducing external workflows that require a stable reference while keeping the original value in a restricted system.

## Approval and review

The application owner and designated security or data-protection reviewer should confirm the data classifications, protection coverage, and any accepted exceptions. Record the approval reference, approver, date, and conditions in the IP Safe submission.

Before sign-off, collect deployment evidence for secret-store access, encrypted PostgreSQL volumes and backups, and a restore that can read encrypted application records. Record how historical plaintext will be protected or migrated.

## Encryption key rotation

Schedule key rotation in the deployment secret store on the approved 30–90 day cadence. Record the key version and activation date without logging key values. The application writes with `DATA_ENCRYPTION_KEY` and can decrypt older data with the comma-separated keys in `DATA_ENCRYPTION_PREVIOUS_KEYS`. Both settings support injection or a mounted secret via their `_FILE` settings.

For a rolling deployment, distribute the new key to every instance in the decryption list before making it active. Then activate it for writes and retain the old key in the decryption list. Verify that new writes and historical reads work. Remove a prior key only after affected records and retained backups have been re-encrypted or expired and restore access has been verified. This application supports the key transition. Secret-store scheduling and historical re-encryption require separate operational evidence.

Reassess the design when data classifications, integrations, export audiences, retention requirements, or key-management requirements change, and during scheduled security reviews.
