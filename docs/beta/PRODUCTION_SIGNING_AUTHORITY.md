# Quantum Studio production signing authority

This step implements the private-runtime signing boundary and integrates it with
existing authorized website-activation issuance. It does not deploy a service,
provision secrets, generate a production key, enable production website publication,
or change M1-M10 review, entitlement, device-limit, revocation or online-access rules.
All automated signing examples/tests use synthetic fixture material only.

## Trust and responsibility boundaries

- The public website retains applications, account entitlements, authorization and
  revocation state, immutable published envelopes, and purpose-specific operator
  credentials. It never receives the licence private signing key or its runtime
  secret binding.
- A separate private signing runtime holds the persistent Ed25519 identity supplied
  by an external secret manager. Application code neither generates nor writes that
  private key. Persistence, access controls, backup and recovery belong to the
  independently approved provisioning system.
- Desktop builds receive only the approved origin and environment-bound PUBLIC
  trust manifest described in `PRODUCTION_CONFIGURATION.md`. The existing verifier
  authenticates envelope signatures and device binding. A valid signature/cached
  envelope alone still cannot authorize protected work: fresh online authorization
  remains mandatory, with no offline grace.
- Trusted private issuance code fetches authoritative website activation/entitlement
  records through the existing authenticated transport before calling issuance.
  This module is not an HTTP endpoint accepting arbitrary caller-provided grants.

`operator_tools/licence_manager/signing_runtime.py` is operator-only code, outside
`website/` and the desktop backend. Existing customer packaging excludes the
`operator_tools` tree. Do not add this module or private bindings to public bundles.

## Interface and issuer model

`LicenceSigner` is a small protocol exposing `environment`, `mode`, `kid`,
`public_key`, `status()` and `sign_licence(payload) -> envelope`. Business decisions,
state transitions, entitlement derivation, transport and persistence do not belong
inside the crypto implementation.

`RuntimeEd25519Signer` implements this interface for staging/production. It parses
strict runtime configuration, derives the public key, checks the independent
public pin, and performs an Ed25519 signing/verification self-test at construction.
Each signing operation takes a detached payload snapshot, signs the existing
canonical JSON representation, then verifies the actual envelope through the
existing `LeaseVerifier`. No caller-supplied `kid`/signature, unknown payload field,
or unsupported schema is accepted. Crypto/provider failures use fixed safe codes,
never secret values or raw provider diagnostics.

The explicit issuer identifier is the existing signed **`kid`**. It must match
`lic-[a-z0-9][a-z0-9._-]{0,63}` and be stable for one public/private pair. No new
`issuer_id` field or licence-schema version is introduced. The existing
`issuer_label` remains human-readable provenance, not the trust anchor.

`sign_verified_licence` is the independent adapter boundary: it checks environment,
keeps a separate copy of the authorized payload, verifies the returned issuer,
exact payload equality, device binding and signature before returning an envelope.
A future remote adapter cannot silently change grants, dates, limits or identity.
It must implement the same contract and return the same existing envelope shape.

## Runtime configuration contract

These values are for the **private signing runtime only**, not Pages Functions or
the static site build. No real values are included or provisioned here.

| Variable | Requirement | Secret? |
| --- | --- | --- |
| `BETA_ENVIRONMENT` | Explicit `staging` or `production`; must match the key record and running process | No |
| `QS_LICENCE_SIGNING_ISSUER_ID` | Approved stable `lic-...` identifier, written to signed `kid` | No |
| `QS_LICENCE_SIGNING_PUBLIC_KEY` | Approved canonical unpadded base64url raw 32-byte Ed25519 PUBLIC key; must equal the derived key | No; safe for public trust configuration |
| `QS_LICENCE_SIGNING_KEY` | Secret JSON record below, delivered through a secure runtime binding | **YES: entire value** |

Secret record contract:

```json
{
  "schema_version": 1,
  "environment": "production",
  "domain": "licence",
  "algorithm": "Ed25519",
  "private_key": "APPROVED_PRIVATE_RUNTIME_SECRET_ONLY"
}
```

This intentionally invalid placeholder is a format reference, not a usable key.
For staging, the record must say `staging` and contain its independently provisioned
staging key. The encoding is **canonical unpadded base64url of a raw 32-byte
Ed25519 seed**. PEM, DER/PKCS8, hex, padded encodings, 64-byte expanded keys,
duplicate JSON members, extra fields, wrong versions/algorithms/domains, and an
incorrect environment tag are rejected. An approved external provisioning process
must perform any format conversion; the application does not guess or convert it.

`production-signing.env.example` next to the implementation lists the binding
names with empty values. It is a checklist, not an automatically loaded dotenv
file. Never fill or commit it with private material. Supply production secrets
out of band only after separately approved key-custody/provisioning work.

The runtime uses the supplied persistent identity across restarts. The Python
object retains only an in-memory cryptographic key object and public metadata;
it does not save the secret record, create a key file, call DPAPI provisioning,
write a key to SQLite, or log/export private material. Python/runtime memory is
not guaranteed to be securely zeroized. Restrict process access, environment
inspection, crash dumps and debugging with local-variable capture accordingly.

The environment tag/domain prevent accidental TEST or cross-environment imports;
raw Ed25519 bytes themselves have no intrinsic environment/provenance marker.
Never relabel a TEST key, fixture seed or staging secret as production. Independent
provisioning and approval of the public pin remain required operational checks.

## Local TEST behavior

`TestEphemeralAuthority` remains the existing ephemeral local signer, with the
same `test-lic-...` identifiers, signatures and fixture method. Its constructor
and signing methods now require explicit local mode (`test` remains the existing
local alias). An unset/invalid/nonlocal environment cannot construct it, and
changing a process to staging/production prevents an existing TEST object from
signing. No TEST key is generated before that environment check.

`configured_licence_signer()` selects the local signer only when
`BETA_ENVIRONMENT=local` and `QS_TEST_LICENSING=1`; otherwise a deployed profile
requires valid runtime secret configuration and never falls back to TEST. The
existing local worker still uses its explicit `--test-mode` and local-profile
checks and is unchanged. Local helpers continue to work as before.

The existing `ProductionAuthority` in `signing.py` is a separate legacy
DPAPI/authoritative-local-request path. Its storage, UI and policy checks remain
unchanged; it is not silently switched to runtime secrets. The new runtime path
never calls its private key-file storage/provisioning helper. No production key
has been created for either path by this work.

## Production-capable authorized issuance path

Private application composition can use:

```python
from operator_tools.licence_manager.signing_runtime import configured_licence_signer
from operator_tools.licence_manager.issuance import issue_website_activation

signer = configured_licence_signer()
# Obtained through existing trusted operator transport, not from a public payload:
# authoritative_activation, private_database
signed_envelope = issue_website_activation(
    private_database, signer, authoritative_activation,
)
```

`issue_website_activation` extracts the existing M5 checked issuance boundary;
`issue_website_activation_for_testing` remains its TEST-only compatibility entry.
It requires an AUTHORIZED, unflagged/unrevoked activation with matching full device
identity and the existing current fixed entitlement snapshot. Entitlement builders,
90-day duration, device limit and original expiry are reused without policy changes.
Worker eligibility/state-machine reconciliation remains outside the crypto module.
The caller must preserve existing authoritative eligibility and concurrency checks;
a fabricated/stale activation object is not independent authorization to sign.

Public-key metadata, verified envelope, original entitlement snapshot and issuance
audit are committed in the existing transaction. Signature or adapter failures roll
back those writes before publication is possible. Private key/configuration bytes
are never supplied to the database or audit functions.

Retries recover the original stored envelope and verify it using its original
stored public key. They do not create a second signature, licence ID or audit event.
Reusing an issuer ID with different public bytes fails closed. Immutability means
that stored signed bytes are recovered unchanged and edits fail verification;
returned Python dictionaries are ordinary detached JSON objects, not frozen objects.

This step does **not** change `beta_worker.py` or open production website endpoints.
The existing TEST metadata/publication/retrieval gates still reject production.
The new authorized issuance API is usable by a separately composed private runtime;
a production orchestration/transport adapter and production-capable publication
remain subsequent work, rather than bypassing those gates here.

## Future separate Cloudflare signing Worker

The public Pages/Functions deployment can be retained. A separate signing Worker
(or equivalent private service) should own its secret binding, distinct deployment
identity, separate staging/production keys and narrowly authenticated invocation.
It must fetch/revalidate authoritative authorization/entitlement facts, preserve
existing concurrency/idempotency rules, and call the same issuance/signing contract.
Do not expose a generic internet-accessible endpoint that signs caller-chosen grants.

The Python implementation is Qt-free and transport-independent. It can run in a
private Python service, or provide canonical-envelope compatibility fixtures for a
Cloudflare Web Crypto adapter. This step supplies no Worker, HTTP API, service token,
network transport, remote secret provisioning or Cloudflare deployment. Any future
adapter must preserve the exact canonical JSON bytes, raw Ed25519 key semantics,
public pins, existing `kid`/schema and verification-before-publication behavior.
The public website receives only the final envelope and public metadata.

## Rotation and failure modes

Before rotation, distribute a desktop trust manifest containing both the old and
new approved public keys. Provision the new private identity externally under a
**new** issuer ID and activate it only after release/acceptance approval. Retain
historical public keys and original envelopes for verification/retry; never re-sign
an existing activation under the new issuer. New authorized replacement activations
inherit the original account entitlement expiry. Remove old signing access when
appropriate, independently of retaining verification trust. Separate staging and
production databases, keys, credentials and deployment identities remain mandatory.

Missing issuer/key/public pin, malformed encodings/records, mismatched derived
public key, TEST settings or provenance, wrong environment, invalid payloads,
changed signed fields, invalid signatures, conflicting immutable metadata, and
unavailable original public trust all fail closed. No fallback signer, key
creation, silent rotation, unsigned envelope, extra grant or offline grace follows.

Remaining production blockers include separately approved key custody/provisioning,
private service authentication/orchestration, production metadata/publication/
retrieval adapters, real email delivery, audit-listed OTP/OAuth hardening, actual
external configuration, release public-trust provisioning and a real HTTPS
acceptance pilot. This document does not certify a production deployment.
