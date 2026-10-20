# Milestone 7: TEST signed licence delivery and offline reuse

## Baseline and architecture

Inspected clean `beta-hardening-v0.2` HEAD `bfacda6`, following the manually
verified Milestone 6. M5 retains the original signed envelope and stable
activation-to-licence mapping in the local operator database. M6 authenticates
through the browser and returns activation status; it does not grant a lease.
`LeaseVerifier` authenticates signature/device binding, `EntitlementPolicy`
checks validity, and `LeaseStore` already caches signed envelopes for startup.
Production trusted keys remain empty.

M7 adds only delivery: Licence Manager signs through the unchanged M5 action;
the website distributes an immutable public artifact; the desktop verifies and
installs it through the existing licence service. No automatic issuance, second
human approval, production signing, new licence format or alternate feature
policy is added. Website AUTHORIZED/ISSUED metadata never grants entitlement.

## Publication

`POST /api/operator/activations/:activationId/publish` accepts exactly
`{schema_version: 1, envelope: <existing M5 signed envelope>}`. Publication uses
new dedicated `OPERATOR_LICENCE_PUBLISH_TOKEN` / manager
`QS_OPERATOR_LICENCE_PUBLISH_TOKEN`, distinct from read and metadata credentials.
The UI's Publish signed licence first runs the existing M5 metadata sync, then
publishes the stored artifact. It never invokes signing. The local helper checks
the original recorded public key/signature/device binding and an explicit field
allowlist before transmitting anything. The endpoint checks activation identity,
AUTHORIZED status and matching ISSUED metadata. This TEST foundation supports the
existing M5 envelope fields; adding future envelope fields requires an explicit
compatible contract extension.

Additive D1 migration `0008_licence_delivery.sql` creates `published_licences`:
activation primary key, unique licence ID, canonical signed JSON, SHA-256,
publication timestamp, PUBLISHED status. A repeated identical artifact succeeds
without changing its timestamp or JSON. Conflicts fail rather than replacing a
record. The website does not sign, supply desktop trust, or assert cryptographic
entitlement. The desktop independently verifies every delivered artifact.

Both publication and delivery are enabled only for local/test website environments.
Production is denied, including fail-closed HTTPS checks. Examples contain only
an empty credential placeholder. No private signing/device key, seed, operator
PII/data key, or DPAPI material is part of publication or retrieval payloads.

## Device proof and retrieval

1. Cookie-free POST `/api/licence/device-challenge` sends `installation_id` and
   optionally the M6 `activation_request_id`. The server selects exactly one
   AUTHORIZED activation with the matching full public-key hash. Unknown,
   revoked, flagged, hash-incomplete or ambiguous registrations are rejected.
2. The server returns a 120-second challenge with schema version, fixed purpose
   `quantum-studio:licence-retrieve:v1`, random 256-bit challenge ID and nonce,
   activation ID, installation ID, full public-key hash and expiry. The exact
   canonical message is retained in `licence_device_challenges` with consumed
   state. Old challenges are cleaned in bounded batches after retention.
3. `DeviceIdentityService.sign_licence_challenge` validates the domain, fields,
   binding and expiry, then loads the EXISTING protected Ed25519 key. It does
   not create a missing key or expose private bytes. It signs canonical JSON
   and returns challenge ID, installation ID, raw public key and signature
   encoded as canonical unpadded base64url. There is no generic signing API.
4. POST `/api/licence/device-retrieve` verifies public-key SHA-256, the short
   installation ID convention, Ed25519 proof, expiry and atomic single use.
   It rechecks activation status and immutable publication/metadata binding.
   Knowing an activation ID alone cannot download a licence.
5. A valid proof returns only `state: pending`, or `state: available` with the
   original signed envelope and its SHA-256. A pending attempt also consumes
   its proof; a fresh challenge makes repeated checks safe. There is no browser
   cookie, operator credential, account PII or issuer trust key in the response.

Quotas share the existing technical rate-limit table with distinct bucket names:
20 challenges per five minutes and 60 proof submissions per minute per edge-IP
bucket. Only a salted IP hash is stored. JSON bodies/responses are bounded,
errors use controlled codes, and redirects cannot forward proofs. Desktop HTTPS
is mandatory except explicitly enabled loopback HTTP for local QA.

## Explicit TEST trust

Production `LicensingService.production()` is unchanged and never reads TEST
trust settings. The application composition root enables local TEST trust only
when BOTH settings are explicit:

- `QS_TEST_LICENSING=1`
- `QS_TEST_LICENCE_TRUST_FILE=<absolute local public-key file>`

Select an existing issued row in Licence Manager and use Export TEST trust.
The file contains only schema version, `domain: test-licence`, Ed25519 algorithm,
original `test-lic-...` key ID and public key. It is selected locally, never loaded
from a website response. Missing/malformed/wrong-domain trust fails closed. The
Account / Licensing panel clearly marks TEST LICENSING.

The trust file can be exported after desktop activation. Check licence reloads
only that configured LOCAL TEST file when a signed envelope becomes available;
pending metadata needs no issuer key. Production cannot invoke this reload.
Thus issuing after activation does not require an extra desktop restart merely
to load the explicitly configured file. The original key can verify an old M5
envelope after the operator signer restarts; no re-signing occurs. Export uses
the selected licence's persisted public metadata, not a new process's key.

## Desktop install and offline behavior

After an M6 AUTHORIZED result, Account / Licensing automatically performs a
separate proof/retrieval transaction. FLAGGED/REVOKED skips retrieval and blocks
manual delivery for that result. Check licence supports explicit retries without
browser login. All transport runs in cancellable workers. Cancellation is checked
before installation; a valid cached entitlement is not removed by a network error.

The service deep-copies the input, verifies trusted signature and exact device
binding, then uses the SAME validity decision as the existing feature policy.
Invalid signature/issuer/device, expired/not-yet-valid/offline-expired or
clock-validation-required envelopes are rejected before persistence. A different
installed/cached envelope is not silently overwritten, including a damaged cache.
A failed cache write never grants an in-memory lease. Reinstalling the identical
valid envelope is idempotent. Only after verification and successful persistence
does the normal service expose the entitlement.

Restart uses the same DPAPI device identity and existing LeaseStore load path.
The locally configured trusted key verifies the cached signature and binding;
normal policy checks dates and clock state. No website, browser sign-in or network
request is needed for a valid cached licence. Diagnostics/UI report Active,
Expired, Invalid licence or Auth Required rather than treating every parsed lease
as active. Plan, UTC expiry and licence ID remain visible. With Active cache,
Sign in / Activate is not presented as the required primary action.

## Exact local manual QA

Use the normal Windows account and the same runtime-data root across restarts.
For negative tests use isolated runtime roots rather than altering real data.

1. In ignored `website/.dev.vars`, retain working M6 local auth configuration.
   Add a NEW `OPERATOR_LICENCE_PUBLISH_TOKEN`; keep read, metadata and publication
   credentials distinct. Set `BETA_ENVIRONMENT=local` and use one consistent
   origin, for example `http://localhost:8788`.
2. From `website`, run `npm run d1:migrate:local` (LOCAL ONLY), build with
   `CLOUDFLARE_LOCAL=true`, then `npm run pages:dev`. Use Pages Functions rather
   than a standalone static/Docusaurus development server.
3. In the operator terminal configure `QS_OPERATOR_WEBSITE_URL`, read token
   `QS_OPERATOR_SYNC_TOKEN`, metadata token `QS_OPERATOR_LICENCE_SYNC_TOKEN`,
   and NEW publication token `QS_OPERATOR_LICENCE_PUBLISH_TOKEN` to match local
   bindings. Launch `.venv\Scripts\python.exe scripts/run_licence_manager.py
   --test-mode --test-data-root C:\Temp\QuantumStudio-M7-Operator`.
4. Choose an absolute TEST trust file path in an existing local folder. It may
   initially not exist. In the desktop terminal set:

   ```powershell
   $env:QS_WEBSITE_URL = 'http://localhost:8788'
   $env:QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP = '1'
   $env:QS_TEST_LICENSING = '1'
   $env:QS_TEST_LICENCE_TRUST_FILE = 'C:\Temp\QuantumStudio-M7-issuer.json'
   .\.venv\Scripts\python.exe -m frontend.main
   ```

5. Open Help -> Account / Licensing -> Sign in / Activate. Complete normal
   website login and explicit device confirmation. Use an APPROVED linked beta
   application. Verify AUTHORIZED; until an artifact is published, licence stays
   pending and no feature entitlement is granted.
6. In Licence Manager refresh website activations, select this device and Issue
   test licence exactly once. Record its local licence ID. Export TEST trust to
   the SAME configured local path, then Publish signed licence. This first syncs
   M5 metadata and then publishes with the distinct delivery credential.
7. Click Check licence on the desktop. Verify TEST LICENSING, Licence status:
   Active, plan, UTC expiry and the matching licence ID. Record device ID too.
8. Close Quantum Studio and STOP local Pages. Restart Quantum Studio with the
   same Windows account, data root, TEST flag and trust-file path. Verify the
   same device and licence IDs, Active offline status, and existing policy-granted
   capabilities. No browser login is required for this restart.
9. Start Pages again and Check licence. Repeat publication if desired: it must
   return already_current, keep the same digest/licence and create no duplicate.
   An operator restart must recover the original licence and trust key, never
   replace its envelope with a newly signed one.
10. Exercise pending, FLAGGED, wrong trust key/signature/device, replayed proof,
    expired licence and network failure using disposable fixtures. Invalid
    deliveries must never be installed. Preserve conflicting/damaged caches for
    explicit recovery; this milestone supplies no automatic overwrite/renewal.

No browser-console POST, browser-cookie copying or manual private-key handling
is part of this procedure. Real browser click-through remains distinct from
automated Qt/HTTP/offline process verification and must be recorded explicitly.

## Validation and limitations

Coverage includes a real M5-issued envelope published through actual endpoint
code and SQLite, cross-language canonical digests, Ed25519 proof verification,
conflict/replay/substitution rejection, explicit trust, validity, persistence
failure, offline cache reopening and UI installation/pending/FLAGGED behavior.
An isolated Windows smoke uses real DPAPI proof, a loopback delivery fixture,
and separate install/offline processes; a canonical offscreen desktop launch
shows the verified cached TEST licence Active. The fixture is not a real browser
login or full manual Pages click-through.

TEST issuer private keys remain ephemeral. Losing the original public-key
metadata/trust configuration prevents verification; it never justifies replacing
an existing licence automatically. No production trust/issuance/deployment,
automatic signing, renewal, account session persistence or key rotation is added.
A cached offline licence continues according to signed expiry/offline policy if
a website device is later revoked; online retrieval fails closed, but instant
offline revocation is not claimed. Linux still has no configured production
secure store and fails closed. Clock rollback is not repaired by redownloading
the same old artifact. Ambiguous installations across accounts require a fresh
M6 activation to select the intended transaction. Operator network actions retain
the existing bounded synchronous UI pattern; desktop delivery is asynchronous.


## Implementation validation and file manifest (2026-10-20)

- Focused M7: 41 desktop/operator tests and 18 website delivery tests passed.
- Full licensing: 228 passed, 4 skipped, plus 8 passing subtests.
- Full website: 158 passed. Typecheck and website build passed.
- Desktop/operator import and canonical offscreen startup passed.
- Isolated real Windows DPAPI proof/install/offline-process and pending-to-Active
  default-dialog checks passed. These use a local HTTP delivery fixture and do
  not constitute real browser/Pages manual verification.
- Local D1 migration 0008 applied. No remote migration/deployment, commit or push.
- `git diff --check` passed; newly added sources were also checked for trailing
  whitespace and a final newline.

Public API extensions are the narrow device-proof method, policy validity
check, delivered-envelope installation and gated local TEST trust reload.
Production trust and M5 issuance signatures/behavior are unchanged. No Builder,
Device Builder, renderer, calculation, geometry or `.qs` schema code changed.
Application-shell integration and the shared SQLite test adapter are in scope.

Added files:

- `backend/licensing/connectors/licence_delivery.py`
- `backend/licensing/licence_delivery.py`
- `backend/licensing/local_test_trust.py`
- `docs/beta/LICENCE_DELIVERY.md`
- `operator_tools/licence_manager/licence_delivery.py`
- `tests/licensing/test_licence_delivery.py`
- `website/functions/_lib/licence-delivery.js`
- `website/functions/api/licence/device-challenge.js`
- `website/functions/api/licence/device-retrieve.js`
- `website/functions/api/operator/activations/[activationId]/publish.js`
- `website/migrations/0008_licence_delivery.sql`
- `website/tests/helpers/sqlite-d1.mjs`
- `website/tests/licence-delivery.test.mjs`

Modified files:

- `backend/licensing/device_identity.py`
- `backend/licensing/policy.py`
- `backend/licensing/service.py`
- `docs/beta/DESKTOP_ACTIVATION.md`
- `docs/beta/LICENCE_MANAGER_ARCHITECTURE.md`
- `frontend/app/account_dialog.py`
- `frontend/main.py`
- `operator_tools/licence_manager/main_window.py`
- `website/.dev.vars.example`
- `website/tests/desktop-auth.test.mjs`
