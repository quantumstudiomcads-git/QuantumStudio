# M9C: desktop online device authorization

A verified signed licence alone no longer makes the desktop Active. No offline grace,
7-day allowance, elapsed-time reconstruction, billing, renewal, self-service,
production signing, or periodic background polling is added.

## Database and API

Apply `0012_device_status.sql` after M9B. It adds activation `authorization_revision`
(default 1 for existing history), a trigger incrementing it only when status changes,
and a separate single-use `device_status_challenges` table. Entitlement revision,
application approval, device-slot counting, signed envelopes, existing delivery
challenges, and foreign keys are unchanged. An old REVOKED row remains terminal.

Both endpoints require HTTPS except explicitly configured local/test loopback HTTP.
No operator token, browser cookie, or browser login is used by the desktop status flow.
Requests use JSON and the existing bounded M7 transport/rate-limit primitives.

`POST /api/licence/device-status-challenge`:

```json
{"installation_id":"dev_<32 hex>","licence_id":"lic_<uuid>","envelope_sha256":"<64 hex>"}
```

The valid cached grant identifies its historical activation by licence ID, including
when the same physical device has since acquired another activation. An optional
`activation_id` further narrows selection. For a device without an artifact,
`activation_id` is required when licence_id is null; envelope_sha256 may be null.
A status-only response never grants access without a verified signed envelope.

The response contains exactly `challenge`: schema_version, purpose
`quantum-studio:device-status:v1`, random challenge_id and nonce (256 bits each),
activation_request_id, installation_id, device_public_key_hash, licence_id,
envelope_sha256, server_time, and expires_at. Lifetime is 120 seconds. The desktop
validates the purpose/binding and reloads its existing Ed25519 private key to sign
canonical JSON. It never generates a replacement key for a proof.

`POST /api/licence/device-status` accepts the same four proof fields as M7:
challenge_id, installation_id, public_key, signature. The server verifies the full
public-key hash, installation ID, signature, expiry, and domain, then consumes the
challenge with a conditional update. Replays/concurrent second use fail. M7 delivery
and M9C status challenges cannot be exchanged. Current activation, publication binding,
and entitlement are read after consumption, including revocation racing the challenge.

A successful response has exactly:

- schema_version, challenge_id
- activation_id, installation_id, device_public_key_hash
- authorization_state (AUTHORIZED/REVOKED), authorization_revision
- licence_id, envelope_sha256
- entitlement_id, entitlement_revision, entitlement_expires_at (Unix seconds)
- revoked_at and reason_code (null for AUTHORIZED)
- server_time and checked_at (Unix seconds)

No envelope, signing key, feature grants, PII, or operator credential is returned.
A revoked device can prove possession and learn REVOKED, but existing M7 delivery
continues denying it an artifact. Rate limiting and no-store responses remain in use.

## Desktop decisions and persistence

At composition-root startup, the cache is verified with existing explicit issuer
trust and the existing protected device identity. Invalid signatures/devices deny
immediately. For valid cached envelopes, one asynchronous startup worker performs
status challenge/proof. Until it completes, the service denies protected work with
Online validation required. The Account / Licensing dialog exposes the resulting
Active, Revoked, Expired, Online validation required, Invalid licence, or Invalid device
state. Check licence on a cached envelope checks status directly, so revoked history
can be learned without attempting artifact delivery. Newly delivered envelopes are
verified/installed and then checked online before becoming Active.

The service verifies exact response schema, challenge freshness/domain, activation,
device ID/full hash, licence ID, and canonical signed-envelope digest. On first
successful validation, authenticated entitlement/activation references are pinned to
that exact grant binding. Subsequent responses must preserve those references, may
not regress revisions/time, and must increment authorization revision when state
changes. Entitlement expiry must equal the immutable signed grant expiry. A status
response cannot broaden signed feature/calculation grants. Challenge reuse, mismatched
or malformed data, proof errors, and stale/conflicting responses fail as invalid
rather than ordinary network outages. An unreachable endpoint is Online validation
required; previous AUTHORIZED success never permits offline use.

`LeaseStore` atomically persists `licensing/device-authorization.json` separately from
the signed envelope, private device key, and trusted clock. Records bind activation ID,
device ID/full hash, licence ID, digest, revision, entitlement reference, checked time,
and revoked timestamp/reason. Records for distinct bindings are retained. REVOKED is
a durable tombstone: restart, old-envelope acceptance, trust reload, Check licence,
and network failure cannot turn that binding Active. A distinct verified binding can
be checked without removing the old tombstone. Existing delivery rules still require
explicit recovery to replace a different cached envelope; M9C adds no automatic
renewal/transfer/replacement UI. Corrupt or unwritable authorization storage fails closed.
These local records are defense in depth, not an offline authorization credential.

Expiry is decided using the authenticated server time against both entitlement and
signed grant bounds. Local rollback requires a fresh online check. Existing trusted
clock/high-water metadata rejects regressions as defense in depth; only signed issue
and authenticated server timestamps advance it. No TPM or offline elapsed-time logic
is used. No cached successful validation is consulted to permit offline work.

## Protected work and running calculations

`LicensingService.can_start_protected_work()` performs a fresh proof transaction on
EVERY call and returns a LicenseDecision. `refresh_online_authorization()` exposes
explicit status refresh; the central policy also denies features/calculations when
state is not Active. Read access through `authorize_read()` remains available.

The gate is wired into calculation authorization before workflow compilation,
Device Builder entry, and immediately before each new single/batch local workflow
launch. Direct headless/external executor integrations must call this same service
before starting new protected work; the generic scientific/HPC executor itself is
not redesigned or given licence/network logic. The final prelaunch checks are bounded
synchronous service calls; startup and Account / Licensing checks use worker threads.

A running workflow is never stopped because authorization changes or the network
fails. A queued batch workflow must validate before its own start; denial stops the
queue from launching additional work. No periodic job/status polling is introduced.
M8 worker issuance, recovery, publication bytes, TEST trust, one-device slot release,
M9A grant dates, and M9B revocation semantics remain intact. Website signing and
production signing are still unavailable.

## Local TEST manual QA

1. Apply all migrations through 0012 without resetting either device's desktop root.
   Restart the website. Preserve both original device identities/caches and issuer
   trust files. Use existing `QS_WEBSITE_URL`, explicit loopback HTTP opt-in, and
   explicit TEST trust settings; no operator token belongs in the desktop.
2. Launch Device A with its original REVOKED activation, cached signed envelope,
   desktop root, and trust. Wait for startup check; Account / Licensing must show
   Revoked. New compute/Device Builder entry must deny; projects/results stay readable.
3. Launch Device B with its AUTHORIZED replacement binding/root/trust. Startup must
   show Active after proof. Its expiry must still be the original account expiry.
4. Stop the website. Restart Device B: Online validation required, no new protected
   work. A previous successful validation must not unlock it offline.
5. Restart Device A offline: Revoked remains visible from its tombstone. Check licence,
   reload original trust, and reload its old envelope: still denied. Restore server
   and verify A remains revoked while B validates Active.
6. Start a legitimate job while B is Active, then stop the website. Do not terminate
   that job. Attempt another new job: it must deny until fresh validation succeeds.
7. Use isolated test fixtures for server-time expiry/clock rollback; do not alter
   real entitlement dates or signed envelopes to simulate renewal.

Automated tests cover protocol proof/replay/expiry/domain separation, real Python
client versus JavaScript endpoints with a real M5 envelope, offline revocation
restart, replacement binding, policy gating, startup/UI, and migration preservation.
Manual two-device click-through is separate and must be recorded explicitly.
