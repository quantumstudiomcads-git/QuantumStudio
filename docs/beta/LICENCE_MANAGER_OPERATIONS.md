# Licence Manager operator guide

## Current gate status

The production signing authority is intentionally unavailable. P1 creates no production licence key and must not be used to issue or deliver real licences. `--test-mode` is for automated tests and disposable demonstrations only; it creates an ephemeral signing key in memory and temporary operator data. TEST ONLY issuance is a separate API and cannot be selected as a production fallback.

The production operator data root is `%LOCALAPPDATA%\QuantumStudio\LicenceManager`. SQLite stores encrypted applicant details, status history, validated activation request fields, licences, public signing metadata, schema migrations, and audit events. Back up the database and DPAPI-wrapped data key together using an approved encrypted backup process. Do not copy the protected files to an untrusted workstation. Applicant email is trimmed, NFC-normalized, case-folded, and NFC-normalized again before keyed indexing. A normalized email may identify only one local application; duplicates are rejected, including rejected applicants, until a separately reviewed reapplication process exists. The keyed index protects equality lookup but, if its key is compromised, likely email addresses can be guessed offline.

The dashboard and Settings inspect only public authority metadata and whether the protected-key blob exists. No files means “Production signing authority is not initialized.” A present protected blob is reported as unverified; file presence is not cryptographic validation. Startup, refresh, applicant review, imports, and profile selection do not decrypt the licence key. A last-authorized-use timestamp is historical evidence from the current manager session, not a check of the current blob.

## Review and activation

Wrap the current website beta-admin applicant export in the strict envelope `{"schema_version":1,"applications":[...]}`. The importer maps the existing D1 export fields, accepts only known version-1 fields, and always assigns new local records `APPLIED`; remote status/review/licence fields never control local state. Review applications locally and approve only after operator review.

Import a version-1 Quantum Studio activation request only after the associated application has been approved. The manager checks request freshness, platform, public key/hash/device ID consistency, schema, and requested profile identifier. The request's requested profile is untrusted intent and never grants entitlement. In Issue Licence, the operator separately selects and confirms either local profile; the choice is recorded in the audit trail before signing. Production issuance accepts only application ID, activation-request ID, a named profile, and confirmation. It reloads and revalidates authoritative rows, device binding, and request integrity under `BEGIN IMMEDIATE`. Entitlements, expiry, issuer, licence ID, and other claims are built internally. Only after those checks does the issuance path DPAPI-unprotect the key and verify it matches the public metadata. The key is not cached and references are released after signing; Python cannot guarantee memory zeroization. Unknown fields cause rejection.

## Issuance and delivery

Review the activation request and its policy profile. Explicitly confirm issuance. In this gate, only test mode can sign. A real future issuance requires a separate Windows key ceremony, protected licence signing key, verified public-key metadata and client trust configuration, and operational approval. Signing, licence persistence, application transition, and issuance audit records commit in one SQLite transaction; a transaction or audit failure rolls them back. Export occurs after commit, so an export failure leaves an issued record that can be exported again idempotently. Licence and receipt are one directory: `<export-root>/<opaque-licence-id>/licence.json` and `receipt.json`. Export stages both files in a sibling directory, syncs them, and publishes the directory by same-filesystem rename. A matching complete directory is an idempotent retry. An incomplete, altered, or unsafe existing directory is never overwritten. Stop delivery, preserve the directory for investigation, compare its licence ID and SHA-256 against the committed record and receipt, and use the approved operator recovery process before retrying. Deliver through a separately controlled channel; the manager never emails applicants.

## Renewal, expiry, and revocation

Initial beta licences last 90 days and bind to one device. Renewal requires a fresh operator review and controlled activation. Local expiry/revocation entries update the administrative record. Revocation does not immediately invalidate an already delivered offline licence; the client enforces its signed expiry until authenticated refresh/revocation exists.

## Audit, recovery, and key loss

Use Audit Log → Verify audit chain before reviewing records. Preserve database and data-key backups as one recovery set. If the workstation or Windows account is lost, restore only under the original protected account where DPAPI permits; otherwise the encrypted PII may be unrecoverable. A lost licence signing key requires a future public-key rotation ceremony and client update; never recreate a replacement with the old key ID. Updater signing recovery is a separate process and key domain.

CurrentUser DPAPI protects against offline access by other Windows accounts, not compromise of the logged-in account/session. The audit chain records tampering but cannot defeat a fully compromised administrator. The issuance boundary limits supported manager code and untrusted imports; it is not Python process isolation. Arbitrary code execution in the operator process or compromise of the Windows account defeats it.

Audit verification detects modified events, removed middle events, and reordering. The current audit head is not anchored outside SQLite. An administrator with database write access can truncate the tail, replace the complete history and recompute its hashes, or restore an older database snapshot without detection. The hash chain is tamper evidence, not append-only immutability.
