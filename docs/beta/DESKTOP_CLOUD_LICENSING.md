# Desktop cloud licence retrieval and verification

## Audit of the existing flow (before this change)

1. `frontend/app/account_dialog.py` already used `DesktopActivationFlow` to start
   a short-lived browser-confirmation flow through `/api/desktop-auth/*`. Website
   login/session authentication stays in the browser; the desktop polls using
   a short-lived device code retained only in memory. It does not store browser
   cookies or receive operator credentials.
2. `DeviceIdentityService` persists the desktop's own Ed25519 device key through
   Windows DPAPI at the existing runtime data root's `licensing/device-key.dpapi`.
   Installation ID is `dev_` plus the first 32 hex characters of SHA-256 of its
   raw public key; full hash is bound to the activation and licence. Proof creation
   reloads the existing key and never replaces an unavailable identity.
3. `LicenceDeliveryService` already called public `/api/licence/device-challenge`
   and `/api/licence/device-retrieve`, proved device possession, checked the
   published digest and installed through `LicensingService`. However, the shared
   Pages gate rejected every nonlocal retrieval with `test_only`.
4. The existing desktop `BETA_ENVIRONMENT`, `QS_WEBSITE_URL`, `QS_LICENCE_TRUST`
   configuration already supported local/staging/production. Deployed profiles
   rejected missing/invalid public trust, wrong environment, TEST trust/settings,
   insecure/placeholder origins and local HTTP exceptions. Local TEST file trust
   was an explicit separate workflow, not a fallback.
5. Signed envelopes were already cached atomically as `licensing/device-lease.json`,
   signature/device-verified on every load, with trusted-clock and authorization
   records stored separately. A conflicting immutable envelope could not silently
   replace an installed one. The cache held no website/operator credentials.
6. `OnlineAuthorization` already used `/api/licence/device-status-challenge` and
   `/api/licence/device-status`, checked challenge/device/licence/digest/revisions,
   kept durable revocation tombstones, and authenticated afresh for each new
   protected operation. Status routes already admitted deployed environments.
   Cached signatures or prior successful status responses never granted offline work.
7. Gaps: deployed retrieval gate, explicit deployed provenance consistency during
   desktop verification, stronger deployed status checks against application/user/
   entitlement/licence state, and classification of temporary HTTP status outages.
   Existing account/licence UI was sufficient and did not need redesign.

## Implementation and endpoints

No endpoint, signing API, new licence schema or login flow was added. Public device
proof endpoints now work in valid staging/production environments; direct TEST
operator metadata/publication routes remain local-only. Desktop never invokes an
operator endpoint, private Worker URL or Service Binding.

The public endpoints are:

- `POST /api/licence/device-challenge`: select the authorized matching activation,
  check deployed eligibility and issue a bounded 120-second device challenge.
- `POST /api/licence/device-retrieve`: verify Ed25519 device proof, atomically consume
  the challenge, re-read authoritative eligibility and return pending or the exact
  published envelope/digest. It returns no new signature or trust material.
- `POST /api/licence/device-status-challenge`: bind a fresh status proof to the
  historical activation, device, licence and immutable digest.
- `POST /api/licence/device-status`: consume valid proof, check current deployed
  application/user/entitlement/licence facts and return existing status/revision/
  authenticated-time fields. No envelope, grants or credentials are returned.

Deployed reads require matching account/application association, an eligible
application, verified active user, the existing fixed beta entitlement, full device
binding, current metadata, matching expiry/device limit, valid publication state,
unchanged artifact digest and a deployed issuer identifier. Revoked licence metadata,
revoked/ineligible application, inconsistent grants and corrupted artifacts fail
closed. Retrieval refuses expired terms. Status can still report an expired term
using authenticated server time so the desktop displays Expired. Local behavior is
preserved; no new restrictions are applied to the local TEST fixtures/workflow.

## Desktop verification and cache boundary

The shared `LicensingService.verify_envelope` boundary now serves installation,
cache load and each online new-work check:

1. Existing `LeaseVerifier` checks schema/required typed fields, trusted `kid`,
   Ed25519 canonical signature and full device ID/hash.
2. In staging/production, require the same issuer/public pin as the selected
   deployment configuration, no TEST mode, and a canonical application UUID whose
   `sub_<application-id>` account/subject references agree. Check the existing beta
   product/channel/plan, device ID/hash derivation, entitlement version and fixed
   concurrent/offline-device policy fields. These are checks of the existing format,
   not new licence fields or grant semantics.
3. Existing installation policy checks not-before, expiry, positive device limits
   and clock state before persistence. Signed grants remain the entitlement source.
   Pages separately checks the signed registered-device limit against current D1.
4. Persist the same signed values through the existing atomic cache. Repeated
   installation preserves the original bytes; conflicting envelopes require the
   existing explicit recovery procedure. Cache loading re-verifies signature,
   device and deployed provenance; malformed/tampered cache grants nothing.
5. Fetch fresh online status. Only valid current authorization can produce Active.
   Installation while status is unreachable can preserve the verified artifact,
   but its state remains Online validation required and protected work stays denied.

Application/activation association is authoritative on Pages after browser-confirmed
activation and device proof. The desktop checks represented signed account/subject/
application references for consistency; it does not infer account ownership from
an untrusted caller-supplied field or newly downloaded key.

## Revocation, replacement and failures

- Every new protected operation revalidates online. An unavailable network or
  temporary HTTP 429/500/502/503/504 status service results in Online validation
  required with NO offline grant. Proof/auth/binding/schema failures remain invalid.
- REVOKED activation state produces Revoked and is retained as the existing durable
  tombstone. Reopening/reloading the old signed cache or going offline cannot undo
  it. A revoked licence marker is rejected by the public state checks; it does not
  invent a new activation transition or rewrite signed bytes.
- Authenticated expiry produces Expired. Read-only project/result access retains
  the existing policy. No offline grace or renewal behavior is added.
- Replacement devices use their own protected identities/new activation histories
  and inherit the existing account entitlement expiry. Old cached licences cannot
  authorize a different device. Same-device history/conflicting cache still requires
  explicit recovery; this change never deletes/replaces a device identity or old
  immutable envelope automatically.
- Account UI keeps its existing layout/statuses. Delivery errors use fixed safe
  user messages; raw HTTP/provider diagnostics are not shown. No operator or signing
  credentials, token values, OTPs or private authority key are logged/returned.

## Exact staging runtime configuration

These are PUBLIC desktop values, safe to ship with an approved staging desktop
configuration. Source runs use the process environment, not Pages `.dev.vars`.
New Windows packages instead load an executable-pinned public profile; see
`WINDOWS_BUILD_PROFILES.md`. Matching process values are allowed, conflicting
overrides are rejected. There is no general-purpose desktop dotenv/secret loader.

The manifest below pins the already committed staging Worker public metadata;
confirm it remains the approved active identity at release. This is a public pin,
not a private secret and not a key fetched from an endpoint.

```powershell
$env:BETA_ENVIRONMENT = 'staging'
$env:QS_WEBSITE_URL = 'https://staging.quantumstudiomcads.com'
$env:QS_LICENCE_TRUST = '{"schema_version":1,"environment":"staging","domain":"licence","algorithm":"Ed25519","keys":{"lic-staging-80b18fccdeb046798d2d85964316d200":"wbXEh-YYK_5MRmp_BG1wqo3OKW5Cq0LLROByidvsPUI"}}'
$env:QS_TEST_LICENSING = '0'
$env:QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP = '0'
Remove-Item Env:\QS_TEST_LICENCE_TRUST_FILE -ErrorAction SilentlyContinue
# Launch the installed Quantum Studio executable from this same PowerShell session.
# For a source checkout, use the repository virtual environment:
.\.venv\Scripts\python.exe -m frontend.main
```

The final staging hostname may not resolve yet. Do not treat a failed DNS lookup as
permission to bypass HTTPS or enable local HTTP/TEST trust. While DNS is pending,
source operators may explicitly configure the already working HTTPS Pages origin instead,
provided it matches the actual deployed website/browser-auth/allowed-origin settings.
There is no hostname fallback or live-DNS dependency in automated tests.

See `desktop-staging.env.example` for the public reference checklist. Use separate
existing data roots via `QUANTUM_STUDIO_DATA_ROOT` for side-by-side local/staging/
production work; do not copy the DPAPI device key between devices or user accounts.
Keep production independently configured with `BETA_ENVIRONMENT=production`, its
approved HTTPS public origin and an environment=`production` public manifest with
independent approved issuer keys. No production origin/key default is introduced.
Keys tagged for one environment cannot be enabled by relabeling TEST material;
independent environment key custody remains an operational requirement.

## Validation and remaining rollout gates

Focused tests cover real RuntimeEd25519Signer envelopes with known synthetic unit
seeds (independent staging/production keys), existing desktop device proof and
connectors, trust rejection, cache tampering/restart, provenance and signature
failure, entitlement expiry, revocation, temporary outages, safe UI errors, and
public-only endpoint use. Public Pages tests use actual SQLite migrations and
real Ed25519 device proofs. Source scans ensure desktop licensing code contains
none of the private authority/provider/operator credential bindings or endpoints.

This is unit/integration and offscreen Qt verification, not real installed staging
click-through or a newly built installer certification. No live DNS, email, Worker,
Pages deployment, new real key or production secret was used/changed. Deployment of
these reviewed Pages changes, correct public runtime/trust configuration, eventual
DNS/HTTPS readiness (or an explicitly configured working Pages origin), and a real
installed-desktop sign-in/issue/retrieve/revoke/replacement acceptance pilot remain
manual rollout steps. Linux still has no production secure device-key store; it
continues to fail closed rather than falling back to a plaintext key.


## Windows packaging follow-up

The exact selected public settings can now be carried by the Windows standalone and
installer without a launch shell. See `WINDOWS_BUILD_PROFILES.md`; changing a packaged
origin requires a reviewed public profile and rebuild. Do not override a staging
package to another hostname with environment variables. Packaged staging has its own
default mutable data root; production retains the existing default root.
