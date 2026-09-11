# B4 licensing and entitlement architecture

B4 controls access to product capabilities without changing Quantum Studio
science, project persistence, or user-owned results. It is an offline-capable
desktop foundation, not a payment, account, or server deployment.

```text
Identity/account -> billing/subscription -> entitlement service -> Ed25519 signer
-> signed device lease -> desktop policy -> catalogue/preparation authorization
-> structured workflow execution
```

The desktop trusts a server-issued signed lease. Local JSON, widget state,
price strings, and environment variables are never authority.

## Components

- `backend.licensing.verifier` canonicalizes JSON and verifies Ed25519 leases
  against a `kid`-selected public-key set.
- `device_identity` creates a device proof-of-possession key; Windows stores it
  as a DPAPI encrypted blob in owned local data, with no plaintext fallback.
- `lease_store` atomically persists the signed envelope and supplemental clock
  metadata below `%LOCALAPPDATA%\QuantumStudio\licensing`.
- `policy` returns typed `LicenseDecision` objects.
- `enforcement` checks selected public intents before `RequestCompiler` runs.
- `frontend.app.licensing_access` guards Device Builder workspace creation.

Scientific compilers, QE adapters, parsers, ResultStore, project schema, and
Builder mathematics contain no licence logic.

## Lease and policy

Schema version 1 signs canonical UTF-8 JSON (sorted keys, compact separators,
non-finite values rejected). The signature covers every field except its
base64url `signature`: `kid`, identity, plan, device binding, time bounds,
grant sets, device/session/offline limits, entitlement version, nonce, trial,
and optional organization/seat fields. Unknown keys, schema, signatures, time
bounds, or device binding fail closed. Multiple trusted public keys support
rotation. Production contains no private signing key; test mocks generate
ephemeral keys.

Implementation state is evaluated before entitlement. A Pro grant for a
planned item returns `NOT_IMPLEMENTED`, never an upgrade prompt. Read access to
existing projects/results is independently allowed after expiry or downgrade.

Leases may provide a shorter offline window. Backwards clock movement returns
`CLOCK_VALIDATION_REQUIRED` and is recoverable after a fresh server lease. An
offline client cannot receive immediate revocation or perfectly coordinate
sessions; future policy bounds this with lease lifetime, offline-device policy,
and server refresh.

Production startup is intentionally fail-closed: no valid lease means no paid
execution. Test/development grants require explicit dependency injection; there
is no environment-variable, build-channel, or static-key unlock. Future beta
access is a short-lived signed entitlement, not an unlocked executable.
