# Quantum Studio Licence Manager architecture

The Licence Manager is an operator-only PySide6 desktop application launched with `scripts/run_licence_manager.py`. It is outside the customer frontend and has no network listener, public API, website integration, customer bundle entry point, or automatic email delivery.

## Trust domains

1. The public website collects applications and exports versioned application records. It cannot approve, issue, or sign licences and receives no private key.
2. The local manager encrypts applicant data, records review decisions, imports device activation requests, derives allowlisted profiles from the canonical calculation catalogue/backend registry, records issuance metadata, and requests a signature through a local authority interface.
3. The local licence authority is a separate Ed25519 domain (`lic-` key IDs in production). Its only production issuance entry point accepts an application ID, activation-request ID, named profile, and explicit confirmation. It reloads and checks authoritative database rows, derives all signed fields from policy and those rows, then loads the DPAPI-protected signing key and signs inside the same SQLite transaction as the issuance, transition, and audit records. The general-purpose client lease helper is not exposed as the production authority API. Tests use an explicitly injected, in-memory TEST ONLY signer; production mode never falls back to it. There is no production key ceremony or automatic production key generation. Updater signing remains independent.

This is an in-process application boundary: imported data cannot directly choose signed claims, and supported manager code has no production API for arbitrary-payload signing. Python does not isolate code within the process; arbitrary code execution in the operator process or compromise of the Windows account defeats this boundary.

The existing client licence verifier authenticates canonical JSON envelopes and device binding. The manager retains that schema and adds policy metadata as signed fields. It supplies explicit entitlement lists; it does not use wildcard grants. A request's `requested_profile` is never authorization: the operator makes a separate audited local profile decision before issuance.

## Data and PII

Production SQLite and the DPAPI-wrapped data key live beneath `%LOCALAPPDATA%\QuantumStudio\LicenceManager`. Applicant fields are serialized as one AES-256-GCM authenticated ciphertext. The email lookup index is an HMAC derived from the random data key. Audit details contain opaque IDs and controlled reason codes rather than PII. Private licence signing keys are never stored in SQLite.

Windows CurrentUser DPAPI ties access to the Windows user account. It does not protect data after that account or session is compromised. A workstation backup must protect the encrypted database and DPAPI-wrapped data key together. Restoring them under a different Windows account may not be possible.

Unsupported operating systems fail closed for production storage and signing. Tests inject a test-only data key and ephemeral signer. Test fixtures use reserved `example.test` addresses only.

## Audit and revocation

Audit events use canonical serialization and a SHA-256 previous-event chain. Verification detects ordinary changes to rows or ordering. A hash chain is tamper evidence; it does not prevent alteration by a fully compromised administrator who can rewrite the database and recompute the chain.

Revocation records the operator's local administrative decision. A delivered offline licence remains usable until its signed expiry unless a later authenticated client refresh/revocation mechanism is implemented. Current controls are 90-day expiry, device binding, controlled renewal, operator audit, and no automatic transfer.

## Customer package boundary

Windows and Linux package audits reject paths containing the operator tool or manager package. These are package-content checks and focused plan tests, not proof from a completed customer build. The customer front end does not import this package. The manager is intended to remain excluded from customer Nuitka bundles, installers, AppImages, update manifests, release ZIPs, Engine Packs, and website builds.
