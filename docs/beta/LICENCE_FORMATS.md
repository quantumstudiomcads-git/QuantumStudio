# Licence Manager versioned formats

## Website applicant import v1

Top-level exact shape: `{"schema_version":1,"applications":[...]}`. Each application uses the current website D1 export names: `application_id`, `full_name`, `email`, `institution`, `country`, `academic_role`, `research_area`, `intended_evaluation`, `operating_system`, consent/version fields, and submission timestamps. The current beta-admin exporter emits a bare array; wrap that array as `applications` and add `schema_version: 1` before import. Existing remote status, review, licence, expiry, and revocation fields may be present in the exported row but are discarded. New local records always start at `APPLIED`.

Applicant IDs are UUIDs. Unknown fields fail the import. The local content hash covers submitted application fields, not remote review/issuance metadata. PII is encrypted before writing to SQLite.

Imports are strict UTF-8 and at most 2 MiB per applicant export with no more than 1,000 rows, 8 nesting levels, or 1,000 items in any collection. String limits are: name 256, email 254, institution 512, country 128, academic role 128, research area 512, intended evaluation 2,048, operating system 64, consent values 16, consent versions 32, and submission timestamp 40 characters. Duplicate JSON keys, non-finite numbers, control characters (except tab/CR/LF in text fields), and oversized data are rejected. Each email is trimmed, NFC-normalized, case-folded, NFC-normalized again, and validated before keyed indexing. No provider-specific alias rewriting is performed. Duplicate normalized email identities are rejected; reapplication requires a future reviewed replacement workflow.

SQLite PII uses a JSON envelope with `version: 1`, a 12-byte random AES-GCM nonce, and ciphertext including its 16-byte authentication tag. AAD canonically binds the stable application/schema identifier `operator.sqlite3/applicants/encrypted-pii-v1`, `applicants` table, record ID, `encrypted_pii` field, and format version. Legacy unversioned ciphertext is rejected; no production database migration has been performed.

## Activation request v1

Exact fields: `schema_version`, `request_id`, `application_id`, `product`, `application_version`, `platform`, `device_id`, `device_public_key`, `device_public_key_hash`, `requested_profile`, and `created_at`. The Ed25519 public key is base64url raw 32-byte data. Its lowercase SHA-256 digest must equal `device_public_key_hash`, and `device_id` must equal the existing client convention `dev_` plus the first 32 digest hex characters. Supported platforms are `windows-x86_64` and `linux-x86_64`; requests expire after 30 days.

Unknown fields, unsupported profile identifiers, conflicting request IDs, malformed identifiers, or requests for an unapproved application are rejected. `requested_profile` is untrusted applicant intent only; import stores no entitlement authorization. A local operator must separately choose and audit the profile before issuance. Exact duplicate request content is idempotent and audited.

Activation files are at most 64 KiB, with at most 8 nesting levels and 1,000 items per collection. String limits are: product 32, application version 64, platform 32, device ID 36, base64url public key 43 (decodes to exactly 32 bytes), public-key hash 64, requested profile 32, and timestamp 40 characters. Import reads are bounded before JSON parsing.

## Signed licence v1

The existing client `DeviceLease` required fields and canonical JSON signature remain authoritative. The manager signs explicit feature/calculation lists plus `product`, `channel`, opaque `subject_id`, `approved_application_ref`, `policy_profile`, and `issuer_label`. No applicant PII, private key, or operator credential is included. `not_before`, `expires_at`, and `offline_until` are Unix UTC seconds. `kid` resolves only in the licence trust domain.

## Operator receipt v1

Receipt fields include the opaque licence/application/device references, issue/expiry times, policy profile, explicit feature/calculation entitlement summary, canonical licence-file SHA-256, and issuance audit-event ID. The delivery unit is an opaque licence-ID directory containing `licence.json` and `receipt.json`, published by same-filesystem directory rename. Existing conflicting directories fail closed and require operator recovery; matching complete bundles are idempotent retries.

## Protected local key envelopes v1

The DPAPI-protected key file is an ASCII JSON envelope with exactly `format`, `version`, `purpose`, and `protected_data`. `format` is `quantum-studio-protected-key`; `version` is integer `1`. Signing-key `protected_data` uses canonical unpadded Base64URL; applicant-data-key `protected_data` uses canonical padded URL-safe Base64. The DPAPI plaintext is strict UTF-8 JSON with exactly `format`, `version`, `purpose`, `algorithm`, `key_length`, and `key`; its format is `quantum-studio-key-material`, its version is integer `1`, and `key` is canonical padded URL-safe Base64 for exactly 32 bytes.

The signing purpose and algorithm are `licence-signing-ed25519` and `Ed25519`. The applicant-data purpose and algorithm are `applicant-pii-database-key` and `AES-256-GCM+HMAC-SHA256`. Each configured-path loader validates its outer purpose before DPAPI and its inner purpose after DPAPI. Cross-purpose files, unknown versions, unexpected fields, malformed encodings, and wrong key lengths fail closed. This describes a new format; no production key or production database migration has been performed. CurrentUser DPAPI does not stop arbitrary code running as the same Windows user from calling Windows DPAPI directly.
