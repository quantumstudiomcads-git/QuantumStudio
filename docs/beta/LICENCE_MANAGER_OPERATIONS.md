# Licence Manager operator guide

## Current gate status

The production signing authority is intentionally unavailable. P1 creates no production licence key and must not be used to issue or deliver real licences. `--test-mode` is for automated tests and disposable demonstrations only; it creates an ephemeral signing key in memory and temporary operator data.

The production operator data root is `%LOCALAPPDATA%\QuantumStudio\LicenceManager`. SQLite stores encrypted applicant details, status history, validated activation request fields, licences, public signing metadata, schema migrations, and audit events. Back up the database and DPAPI-wrapped data key together using an approved encrypted backup process. Do not copy the protected files to an untrusted workstation.

## Review and activation

Wrap the current website beta-admin applicant export in the strict envelope `{"schema_version":1,"applications":[...]}`. The importer maps the existing D1 export fields, accepts only known version-1 fields, and always assigns new local records `APPLIED`; remote status/review/licence fields never control local state. Review applications locally and approve only after operator review.

Import a version-1 Quantum Studio activation request only after the associated application has been approved. The manager checks request freshness, platform, public key/hash/device ID consistency, schema, and requested profile identifier. The request's requested profile is untrusted intent and never grants entitlement. In Issue Licence, the operator separately selects and confirms either local profile; the choice is recorded in the audit trail before signing. Unknown fields cause rejection.

## Issuance and delivery

Review the activation request and its policy profile. Explicitly confirm issuance. In this gate, only test mode can sign. A real future issuance requires a separate Windows key ceremony, protected licence signing key, verified public-key metadata and client trust configuration, and operational approval. Exported files use opaque licence IDs, deterministic canonical JSON, atomic file replacement, and a privacy-minimal receipt. Deliver through a separately controlled channel; the manager never emails applicants.

## Renewal, expiry, and revocation

Initial beta licences last 90 days and bind to one device. Renewal requires a fresh operator review and controlled activation. Local expiry/revocation entries update the administrative record. Revocation does not immediately invalidate an already delivered offline licence; the client enforces its signed expiry until authenticated refresh/revocation exists.

## Audit, recovery, and key loss

Use Audit Log → Verify audit chain before reviewing records. Preserve database and data-key backups as one recovery set. If the workstation or Windows account is lost, restore only under the original protected account where DPAPI permits; otherwise the encrypted PII may be unrecoverable. A lost licence signing key requires a future public-key rotation ceremony and client update; never recreate a replacement with the old key ID. Updater signing recovery is a separate process and key domain.

CurrentUser DPAPI protects against offline access by other Windows accounts, not compromise of the logged-in account/session. The audit chain records tampering but cannot defeat a fully compromised administrator.
