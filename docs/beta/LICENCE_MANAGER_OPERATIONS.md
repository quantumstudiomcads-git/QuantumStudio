# Licence Manager operator guide

## Current gate status

The production signing authority is intentionally unavailable. P1 creates no production licence key and must not be used to issue or deliver real licences. `--test-mode` is for local tests and demonstrations only; without `--test-data-root`, it creates an ephemeral signing key in memory and temporary operator data. TEST ONLY issuance is a separate API and cannot be selected as a production fallback. No supported generic DPAPI unprotect function exists.

The production operator data root is `%LOCALAPPDATA%\QuantumStudio\LicenceManager`. SQLite stores encrypted applicant details, status history, validated activation request fields, licences, public signing metadata, schema migrations, and audit events. Back up the database and DPAPI-wrapped data key together using an approved encrypted backup process. Do not copy the protected files to an untrusted workstation. Applicant email is trimmed, NFC-normalized, case-folded, and NFC-normalized again before keyed indexing. A normalized email may identify only one local application; duplicates are rejected, including rejected applicants, until a separately reviewed reapplication process exists. The keyed index protects equality lookup but, if its key is compromised, likely email addresses can be guessed offline.

The dashboard and Settings inspect only public authority metadata and whether the protected-key blob exists. No files means “Production signing authority is not initialized.” A present protected blob is reported as unverified; file presence is not cryptographic validation. Startup, refresh, applicant review, imports, and profile selection do not decrypt the licence key. A last-authorized-use timestamp is historical evidence from the current manager session, not a check of the current blob.

## Review and activation

Use Applications → **Sync website applications** for the authenticated read-only Website → Licence Manager beta bridge, or retain **Import applications…** for a manually supplied version-1 JSON export. The sync client reads `QS_OPERATOR_WEBSITE_URL` and `QS_OPERATOR_SYNC_TOKEN` from the Licence Manager process environment and sends the token as a bearer credential. The website endpoint's separate Cloudflare binding is `OPERATOR_SYNC_TOKEN`; configure it only as a secret, never in `wrangler.toml`. Local HTTP is restricted to an explicitly local/test run at loopback; production sync requires HTTPS.

The applicant pull reports fetched, newly imported, duplicate, and rejected counts and refreshes the Applications table. Website data still passes through the existing strict `import_applicants_json` validation path; the client does not write SQLite directly. The importer assigns new local records `APPLIED` and website status/review/licence state never controls local decisions.

After locally reviewing an application, select it and use **Sync status to website** to explicitly mirror its current locally stored review status (`APPLIED`, `UNDER_REVIEW`, `APPROVED`, or `REJECTED`). The manager reads authoritative website status from GET on the existing `/api/operator/applications/:applicationId/status` route using the dedicated status-sync credential, then reconciles only valid forward review transitions. For example, website `APPLIED` and local `APPROVED` sends `UNDER_REVIEW` followed by `APPROVED`; each POST still passes website `assertTransition()` and the existing atomic status/audit update. The `X-QuantumStudio-Expected-Status` header guards each POST against concurrent website changes, and local SQLite is rechecked before each step. Terminal or divergent website states are not repaired. Already-current sync adds no transition audit; a partial failure can be retried from a fresh website read. Local approval/rejection works independently of website availability. A failed push leaves the local decision unchanged. Operator messages distinguish authentication, unreachable endpoint, HTTP 409/incompatible history, and unexpected responses without exposing server bodies, credentials or applicant details. Review conflicts before retrying; restore connectivity or the dedicated credential for transport/authentication failures. The write bridge uses the separate `QS_OPERATOR_STATUS_SYNC_TOKEN` setting and Cloudflare `OPERATOR_STATUS_SYNC_TOKEN` secret; never reuse the read-only `OPERATOR_SYNC_TOKEN` or place either real token in `wrangler.toml`. The example file contains only the empty status-token setting.

Website status is a mirror, not the decision authority. TEST issuance metadata sync is described below. Production issuance, remote revocation sync and synchronization of rich signed activation-request files are not implemented. Signing remains entirely local. Production Cloudflare secrets/deployment are not configured.

New beta applications submitted by signed-in users are associated with the authenticated account ID, not matched to an account by email. The account's `/beta-access` page shows a status card instead of another form once its application exists; `/account` includes the same compact status summary. Historical applications with no `user_id` are not automatically backfilled by email and therefore do not appear as linked account applications. Local testing should create a linked application through the authenticated submission flow or use an explicit fixture.

## Automatic beta-device activation

An approved beta applicant can register an installation through the authenticated `POST /api/beta/activation` endpoint. The endpoint uses the signed-in account and its linked application; clients cannot submit an account ID, application ID, activation status, or licence claim. It accepts the desktop's stable installation ID (`dev_` plus the public-key hash prefix), platform, architecture, and application version. No hardware fingerprint is collected. An approved account must have a current fixed account entitlement. Its persisted `device_limit` controls automatic authorization (beta default 1; future limits of 2+ use the same schema). `BETA_MAX_ACTIVE_DEVICES` retains legacy configuration validation but cannot expand an account grant. A non-eligible application or an installation over the limit is flagged for support rather than automatically authorized. Repeating a current registration is idempotent. Revoked activation records remain historical; a new authenticated registration can create a separate activation when the account has a free slot.

The authenticated `/account` page shows each user's own compact device ID, platform, and safe status. The operator's **Activation Requests** page has a separate **Refresh website activations** view that reads through `/api/operator/activations` using the existing read-only `QS_OPERATOR_SYNC_TOKEN` / `OPERATOR_SYNC_TOKEN` bearer credential. It does not add website rows to local activation requests. TEST MODE provides the separate issuance and metadata actions described below. The endpoint requires HTTPS in production; local HTTP use is only for local Pages testing. No production token is configured or committed.

These beta activation records are not the rich signed activation-request files consumed by the local Licence Manager. No automatic issuance scheduler, desktop enforcement integration, remote device revoke/manage action, or production deployment is part of this milestone. Website applications without an authenticated `user_id` remain unlinked; there is no email-based backfill.

For manual import, wrap the current website beta-admin applicant export in the strict envelope `{"schema_version":1,"applications":[...]}`. The importer maps the existing D1 export fields and accepts only known version-1 fields. Review applications locally and approve only after operator review.

Import a version-1 Quantum Studio activation request only after the associated application has been approved. The manager checks request freshness, platform, public key/hash/device ID consistency, schema, and requested profile identifier. The request's requested profile is untrusted intent and never grants entitlement. In Issue Licence, the operator separately selects and confirms either local profile; the choice is recorded in the audit trail before signing. Production issuance accepts only application ID, activation-request ID, a named profile, and confirmation. It reloads and revalidates authoritative rows, device binding, and request integrity under `BEGIN IMMEDIATE`. Entitlements, expiry, issuer, licence ID, and other claims are built internally. Only after those checks does the issuance path read the configured version-1 `licence-signing-ed25519` protected envelope, DPAPI-unprotect it internally, validate its purpose-bound key material and public-key consistency, then sign. The PII key uses the separate `applicant-pii-database-key` purpose. No caller-supplied protected blob is accepted, and no supported operation returns signing-key bytes. The key is not cached and references are released after signing; Python cannot guarantee memory zeroization. Unknown fields cause rejection.

## Issuance and delivery

Review the activation request and its policy profile. Explicitly confirm issuance. In this gate, only test mode can sign. A real future issuance requires a separate Windows key ceremony, protected licence signing key, verified public-key metadata and client trust configuration, and operational approval. Signing, licence persistence, application transition, and issuance audit records commit in one SQLite transaction; a transaction or audit failure rolls them back. Export occurs after commit, so an export failure leaves an issued record that can be exported again idempotently. Licence and receipt are one directory: `<export-root>/<opaque-licence-id>/licence.json` and `receipt.json`. Export stages both files in a sibling directory, syncs them, and publishes the directory by same-filesystem rename. A matching complete directory is an idempotent retry. An incomplete, altered, or unsafe existing directory is never overwritten. Stop delivery, preserve the directory for investigation, compare its licence ID and SHA-256 against the committed record and receipt, and use the approved operator recovery process before retrying. Deliver through a separately controlled channel; the manager never emails applicants.

## Renewal, expiry, and revocation

M9A beta account entitlements last 90 days from approval. Website-path device licences bind to a device and inherit that fixed account expiry, including later/replacement devices; activation never restarts the term. The legacy manually imported request path is unchanged. Renewal requires a fresh operator review and controlled activation. Local expiry/revocation entries update the administrative record. Revocation does not immediately invalidate an already delivered offline licence; the client enforces its signed expiry until authenticated refresh/revocation exists.

## Audit, recovery, and key loss

Use Audit Log → Verify audit chain before reviewing records. Preserve database and data-key backups as one recovery set. If the workstation or Windows account is lost, restore only under the original protected account where DPAPI permits; otherwise the encrypted PII may be unrecoverable. A lost licence signing key requires a future public-key rotation ceremony and client update; never recreate a replacement with the old key ID. Updater signing recovery is a separate process and key domain.

### Database and PII-key pair recovery

Startup takes an exclusive, bounded cross-process storage-initialization lock before inspecting the database, protected data-key file, and pending marker together; it rechecks state after acquiring the lock. On Windows the lock is an exclusively opened per-root file with read/write/delete sharing denied. A process crash releases the operating-system handle; restart validates storage state before recovery. A new storage root is initialized only when both database and key are absent. Initialization creates a versioned, root-bound pending marker with a random non-secret storage-generation UUID, publishes the DPAPI-protected key without replacement, and creates the initial database. The initial schema migrations, generation UUID, and version-1 completion metadata are committed together. The UUID is stored in database metadata and inside the protected key envelope; it is a pairing check, not a secret or decryption credential. The pending marker is recovery coordination data, not proof that an existing database belongs to this operation. If the database is absent, recovery may create it with the already-published matching key. If a database exists, recovery proceeds only when its own metadata has a valid matching UUID, version-1 completion state, and the complete current schema migration set. A database without that evidence, with malformed or mismatched metadata, or with unproven schema completion is not adopted or migrated. Recovery never adds pairing metadata to an unproven database.

- **Database exists, key missing:** stop using the manager and preserve the database unchanged. Restore the exact matching protected key from the approved backup. Do not generate a replacement. Where practical, validate a copied database/key pair in a disposable recovery environment first.
- **Key exists, database missing:** stop and investigate. Restore the matching database backup. Do not let normal startup create a blank database.
- **Both missing:** controlled first-run initialization is allowed.
- **Both present but corrupt or mismatched:** preserve both and restore a matched backup pair. Do not overwrite either automatically.

- **Pending marker with an existing unproven database:** preserve the database, key, and marker unchanged. Initialization stopped because completion and ownership could not be proven; arrange manual inspection or restore a matched database/key backup pair. Do not ask the manager to retry by creating replacement storage.

The manager has no destructive reset or “start over” action. CurrentUser DPAPI neither backs up nor recovers a deleted key. The lock is an initialization coordination mechanism, not a defense against a compromised Windows account or administrator.

CurrentUser DPAPI protects against offline access by other Windows accounts, not compromise of the logged-in account/session. The audit chain records tampering but cannot defeat a fully compromised administrator. The issuance boundary limits supported manager code and untrusted imports; it is not Python process isolation. Same-user arbitrary code can invoke Windows DPAPI directly; arbitrary code execution in the operator process or compromise of the Windows account defeats this boundary. No production key ceremony or production database migration has been performed.

Audit verification detects modified events, removed middle events, and reordering. The current audit head is not anchored outside SQLite. An administrator with database write access can truncate the tail, replace the complete history and recompute its hashes, or restore an older database snapshot without detection. The hash chain is tamper evidence, not append-only immutability.


## Milestone 5 local TEST QA

1. Apply migrations through `0006_beta_activation_licences.sql` to LOCAL D1
   only: from `website`, run `npm run d1:migrate:local`. Never add `--remote`.
2. Configure distinct local website secrets `OPERATOR_SYNC_TOKEN`,
   `OPERATOR_STATUS_SYNC_TOKEN`, and `OPERATOR_LICENCE_SYNC_TOKEN` in ignored
   `.dev.vars`. Matching manager environment variables are
   `QS_OPERATOR_SYNC_TOKEN`, `QS_OPERATOR_STATUS_SYNC_TOKEN`, and
   `QS_OPERATOR_LICENCE_SYNC_TOKEN`. Set `QS_OPERATOR_WEBSITE_URL` to the local
   Pages origin and `BETA_ENVIRONMENT=local` in the manager process. The manager
   does not load website `.dev.vars` automatically. Examples contain empty
   placeholders only, never real credentials.
3. Sign in as a local fixture user with an APPROVED linked application. Submit
   activation facts plus the desktop identity's full public-key hash:
   `{installation_id, platform, architecture, app_version, device_public_key_hash}`.
   The ID must be `dev_` plus the first 32 digits of that 64-digit hash. Existing
   registrations can add the matching full hash by retrying POST; old requests
   remain compatible but cannot be issued until the hash is supplied. Never
   invent a hash or send a private device key. AUTHORIZED is the existing
   automatic entitlement outcome, not another operator approval.
4. For restart QA on Windows launch from the repository with:
   `.venv\Scripts\python.exe scripts/run_licence_manager.py --test-mode --test-data-root C:\Temp\QuantumStudio-M5-Test`.
   Use a new isolated directory, never the production operator directory.
   It uses existing CurrentUser DPAPI storage for the applicant-data key.
   Without this option the default TEST database is temporary and disposable.
5. In Activation Requests, use Refresh website activations, select an AUTHORIZED
   row, and Issue test licence. Its local licence ID appears immediately.
   There is no second approval dialog. FLAGGED/REVOKED or hash-incomplete rows
   are not issuable. Use Sync licence metadata independently. Simulate a failed
   sync or missing write credential and verify the safe specific error. Restore
   configuration and retry; the stored licence is not replaced.
6. Close and relaunch with the same isolated root and Windows account. Refresh
   and select the same activation. Confirm the same local licence ID, disabled
   issuance, enabled metadata retry, and prior-TEST-key notice. The prior signed
   envelope is recovered unchanged. A new ephemeral signer cannot establish
   trust for an old envelope by itself; no automatic re-signing occurs.
7. Retry metadata sync twice and verify `updated` then `already_current` (or
   `already_current` for both if already mirrored). The endpoint accepts exactly
   the seven documented safe fields, authenticates only its dedicated token,
   rejects private/extra fields and rejects conflicting existing metadata.

This milestone does not deliver a production licence, persist TEST signing keys,
update account-wide application approval status, or implement automatic issuance.
The website account device summary continues to show activation status only.
Manual click-through against local Pages/D1 is separate from automated offscreen
Qt/loopback HTTP verification and must be recorded explicitly before freeze.

M9A provisioning, migration and legacy-data instructions: [ACCOUNT_ENTITLEMENTS.md](ACCOUNT_ENTITLEMENTS.md). Online status validation and revocation remain later phases; no offline-grace mechanism is introduced by M9A.
