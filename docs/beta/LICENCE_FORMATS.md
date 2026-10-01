# Licence Manager versioned formats

## Website applicant import v1

Top-level exact shape: `{"schema_version":1,"applications":[...]}`. Each application uses the current website D1 export names: `application_id`, `full_name`, `email`, `institution`, `country`, `academic_role`, `research_area`, `intended_evaluation`, `operating_system`, consent/version fields, and submission timestamps. The current beta-admin exporter emits a bare array; wrap that array as `applications` and add `schema_version: 1` before import. Existing remote status, review, licence, expiry, and revocation fields may be present in the exported row but are discarded. New local records always start at `APPLIED`.

Applicant IDs are UUIDs. Unknown fields fail the import. The local content hash covers submitted application fields, not remote review/issuance metadata. PII is encrypted before writing to SQLite.

## Activation request v1

Exact fields: `schema_version`, `request_id`, `application_id`, `product`, `application_version`, `platform`, `device_id`, `device_public_key`, `device_public_key_hash`, `requested_profile`, and `created_at`. The Ed25519 public key is base64url raw 32-byte data. Its lowercase SHA-256 digest must equal `device_public_key_hash`, and `device_id` must equal the existing client convention `dev_` plus the first 32 digest hex characters. Supported platforms are `windows-x86_64` and `linux-x86_64`; requests expire after 30 days.

Unknown fields, unsupported profile identifiers, conflicting request IDs, malformed identifiers, or requests for an unapproved application are rejected. `requested_profile` is untrusted applicant intent only; import stores no entitlement authorization. A local operator must separately choose and audit the profile before issuance. Exact duplicate request content is idempotent and audited.

## Signed licence v1

The existing client `DeviceLease` required fields and canonical JSON signature remain authoritative. The manager signs explicit feature/calculation lists plus `product`, `channel`, opaque `subject_id`, `approved_application_ref`, `policy_profile`, and `issuer_label`. No applicant PII, private key, or operator credential is included. `not_before`, `expires_at`, and `offline_until` are Unix UTC seconds. `kid` resolves only in the licence trust domain.

## Operator receipt v1

Receipt fields include the opaque licence/application/device references, issue/expiry times, policy profile, explicit feature/calculation entitlement summary, canonical licence-file SHA-256, and issuance audit-event ID. Filenames contain only the opaque licence ID.
