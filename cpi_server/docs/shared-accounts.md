# Shared accounts for CPI and Credit Dossier

Business accounts registered in either application use the Credit Dossier identity
service. Usernames are normalized to lowercase and protected by a database unique
index on `LOWER(users.user_id)`. Concurrent and case-only duplicate registrations
are rejected. CPI stores an identity mirror for ownership and analytics; it does
not store a second working password or independent recovery answers.

Registration requires administrator approval. A CPI administrator approving a CPI
registration also approves the central identity. Dossier administrator approval is
recognized by CPI at the next login. Administrators keep their existing app-specific
sign-in flows; public registration still permits only the two business roles.

Recovery in either application verifies the same three security answers and resets
the same password. Dossier password changes, user resets and administrator resets
increment `credential_version`; existing CPI sessions are rejected on their next
request. Dossier resets revoke its sessions. CPI resets also delete CPI sessions.
Both registration pages and CPI's admin policy screen use the shared password policy.

## Deploying an existing installation

1. Deploy/restart both backends so their additive schema migrations have run.
2. Configure the same server-only `SHARED_DEAL_API_KEY` in both backends and set CPI's
   `SHARED_DEAL_API_URL` to the reachable Dossier backend URL. The identity service
   must be reachable for business-account login, registration and password recovery.
3. Before opening registration, run the migration from `cpi_server/backend`:

   ```text
   python -m app.scripts.migrate_shared_identities
   python -m app.scripts.migrate_shared_identities --apply
   ```

The first command lists legacy accounts without changing them. The second transfers
existing PBKDF2 hashes and security-answer hashes through the authenticated service;
plaintext passwords are neither needed nor printed. Existing passwords continue to
work, and account-owned CPI records stay under their original identifiers.

Independent username collisions stop migration with a conflict. Replace a duplicate
Dossier identity only with explicit authorization, using
`--replace-duplicates <username> ...` together with `--apply`. This adopts the CPI
password, role, approval, lock state and recovery answers, revokes old Dossier sessions,
and preserves the Dossier internal user ID and linked business records. Existing
Dossier passwords for those duplicate identities stop working. Successful imports are
idempotent and cannot overwrite later password changes when rerun.

For this workspace, the authorized replacements were `aegon`, `hela`, and `romi`.
All six legacy CPI business accounts were migrated. They now use their CPI credentials
in both applications.

## Verification

- Dossier database tests exercise registration from both routes, case-insensitive
  duplicate rejection, pending approval, both password reset routes, incorrect answers,
  session revocation, hash migration and explicitly authorized duplicate replacement.
- CPI tests check shared registration/recovery, duplicate handling and rejection of
  sessions whose central credential version has changed.
- End-to-end checks used temporary accounts against the running Dossier service:
  registration from each app, login in both apps, resets from each app, and rejection
  of an old CPI session after a Dossier reset. Temporary test accounts were removed.
