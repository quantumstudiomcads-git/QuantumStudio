# Milestone 6: desktop browser authentication and device activation

## Inspected baseline and boundaries

Started from clean `beta-hardening-v0.2` HEAD `83bccf3` (Milestone 5). The website
uses its existing `qs_session` cookie, normal login/Google/OTP return paths and
origin checks. Desktop startup already constructs `LicensingService.production`
and loads `DeviceIdentityService(production_secure_store(...))`. On Windows this
is the existing DPAPI device key. No second key store or identity is added.

The existing licensing connector supports leases/sessions, and its AuthConnector
is a future OIDC/PKCE contract. This milestone adds a narrow, separate
`DesktopActivationConnector`; it does not falsely implement PKCE or alter lease
connector behavior. The Qt-free `DesktopActivationFlow` is session-only. The
Qt dialog/worker in `frontend.app.account_dialog` owns browser launch and progress.
Help -> Account / Licensing opens the panel in both Hub and Project windows.

The existing Milestone 4 activation operation is extracted as
`registerActivationForUser(env, userId, facts)` inside the same feature module.
Both the existing browser activation route and desktop confirmation call it.
Its automatic entitlement, device-limit, revoked-device and stable-ID behavior
is unchanged. Milestone 5 signing, persistence and metadata semantics are untouched.

## Protocol and routes

1. Desktop POST `/api/desktop-auth/start` sends only the real public facts:
   `installation_id`, `device_public_key_hash`, `platform`, `architecture`,
   `app_version`. The server validates the same activation schema and requires
   the full hash. No client account/application/status claims are accepted.
2. Start returns a random 256-bit `challenge_id`, a distinct random 256-bit
   `device_code`, `verification_url`, `expires_in: 300`, and `interval: 3`.
   The browser URL contains the challenge ID only; the polling secret never
   enters the URL or browser session. The desktop validates that the URL has
   the configured origin, exact confirmation path and challenge query.
3. Desktop opens the system browser at `/desktop-auth?challenge=...`.
   Existing middleware redirects unauthenticated users through normal login
   with that safe return path. GET `/api/desktop-auth/confirm?challenge=...`
   requires the existing website session and returns only public device facts.
4. The page displays the device/platform/version and asks the user to confirm
   only a sign-in they started. Explicit POST `/api/desktop-auth/confirm` sends
   only `challenge_id`, requires the existing cookie session, JSON and the exact
   configured Origin. Account identity comes only from the validated session.
   A conditional PENDING -> PROCESSING claim prevents concurrent confirmation.
   The shared activation operation runs and stores a minimal result. There is
   no new operator/human approval step after beta application approval.
5. Desktop POST `/api/desktop-auth/status` sends challenge ID and device code,
   without Cookie or operator credentials. Pending polls return `pending`.
   Completion returns `completed` plus activation ID, installation ID and
   AUTHORIZED/FLAGGED/REVOKED status. A conditional update consumes the result
   before delivery; later requests return `consumed`. No account identity,
   website session, licence envelope, lease or signing material is returned.
6. Desktop POST `/api/desktop-auth/cancel` authenticates the same bounded secret
   and cancels a pending/in-progress/unconsumed challenge. Local cancellation
   completes even if the server is unavailable; abandoned rows expire.

## Schema and lifecycle

Additive local D1 migration `0007_desktop_auth.sql` adds
`desktop_auth_challenges` and `desktop_auth_rate_limits` without modifying
Milestone 5 tables. Challenges contain ID, SHA-256 device-code hash, immutable
public facts JSON, state, created/expiry/next-poll timestamps, completion and
consumption timestamps, and minimal result JSON. No private key or raw device
code is stored. No browser session is minted by this protocol.

States: PENDING -> PROCESSING -> COMPLETED -> CONSUMED. Failure is FAILED;
explicit cancellation is CANCELLED; the server clock makes every unfinished
challenge invalid at expiry (EXPIRED on access). Browser confirmation accepts
only unexpired PENDING state. Desktop monotonic expiry also rejects responses
that arrive after its local deadline. Terminal client states discard the secret.
Concurrent confirmations cannot run the shared operation twice, and concurrent
polls cannot deliver two successful results.

Start is limited atomically to 10 attempts per five-minute fixed window per
edge IP bucket. Only a salted hash of CF-Connecting-IP is retained. Local
requests without the edge header share a local bucket. Polls are atomically
limited to one per three seconds per authenticated challenge; guessing requires
both 256-bit random values. Request/response bodies are bounded. Start performs
bounded cleanup (100 rows per table per request) of challenge rows older than
one day past expiry and old quota buckets. There is no remote cleanup cron.

## Security and desktop behavior

The desktop never reads browser cookies, uses no CookieJar, persists no auth
code, and sends no operator token. Only the browser's normal website requests
use the existing session cookie. The challenge secret cannot be used as a
normal website session. Facts are fixed when the challenge is created; polling
or confirmation cannot replace the intended device or supply another user ID.
Origin checks, JSON-only confirmation, no-store/no-referrer and anti-framing
headers protect the browser confirmation. Desktop requests require HTTPS;
explicitly enabled local QA permits loopback HTTP only. Redirects are rejected
without forwarding facts or codes. Error messages use controlled codes and safe
text rather than arbitrary response bodies, URLs or credentials.

Network calls run in a cancellable worker, with a five-second request timeout.
The UI shows waiting, authorized, flagged, revoked, expiry, cancellation, browser
failure and network failure. Closing during start cannot subsequently open the
browser. App shutdown waits for bounded worker cancellation. The existing
licensing service is never given a lease or entitlement grant by this flow.

## Local QA

Run migrations locally only from `website`: `npm run d1:migrate:local`.
Use existing ignored `.dev.vars` settings for the normal local website auth;
no new signing/operator secret is needed. Configure `BETA_ALLOWED_ORIGIN` as
`http://127.0.0.1:8788` (or use localhost consistently in both website and desktop settings) and use the existing local test authentication settings.
For a local Pages build in PowerShell:

```powershell
$env:CLOUDFLARE_LOCAL = 'true'
npm run build
npm run pages:dev
```

The browser must use Pages Functions, not only the Docusaurus development server.
In a second terminal at the repository root:

```powershell
$env:QS_WEBSITE_URL = 'http://127.0.0.1:8788'
$env:QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP = '1'
.\.venv\Scripts\python.exe -m frontend.main
```

1. Open Help -> Account / Licensing -> Sign in / Activate.
2. Confirm the system browser opens. Sign in through normal website login if
   needed. The local fixture account needs a linked, APPROVED beta application.
3. Review the shown device and click Confirm desktop activation.
4. Return to Quantum Studio and verify AUTHORIZED. `/account` should show the
   same stable installation. No browser-console POST is needed.
5. Restart Quantum Studio under the same Windows account/runtime data root;
   repeat activation and check the installation remains identical.
6. Exercise cancellation, closing during start, no connection, five-minute
   expiry, and an over-limit device (FLAGGED). Existing revocations remain so.
7. Verify that activation alone does not install a licence or unlock features.

## Validation and limits

Focused tests cover real SQLite/D1 SQL, random IDs, login redirect/session,
origin/CSRF, expired/consumed/invalid states, device substitution, quotas,
concurrent confirmations/result consumption, automatic first-device approval,
over-limit flagging, and unchanged Milestone 5 metadata. Desktop tests cover
real public identity reuse, cookie-free HTTP, unsafe URLs/redirects, terminal
states, late results, cancellation and offscreen Qt/browser failure behavior.

Real browser click-through remains a distinct manual QA requirement. Linux has
no production secure device store configured in the existing foundation and
continues to fail closed; tests inject identities, never add a plaintext
fallback. Device proof-of-possession, licence retrieval, automatic issuance,
lease installation, production signing and deployment remain deferred.

A lost completion response after consumption requires a new sign-in challenge;
existing activation registration is idempotent, so this does not add a device.
A process failure during PROCESSING requires expiry/restart. Cancellation cannot
undo an activation that already committed concurrently. No long-lived desktop
account session or activation result is persisted; only the existing protected
device identity persists. NAT users share start quotas. Rate-limit configuration
and scheduled cleanup can be expanded in a later operational milestone.


Validation performed during implementation: focused desktop tests, real-SQLite
website challenge and browser adapter tests, full licensing and website suites,
TypeScript checking, website production build, import smoke and diff whitespace
checks. An isolated Windows DPAPI smoke verified identical public identity over
two separate process starts. A timed offscreen launch of `frontend.main` opened
and closed the actual Help -> Account / Licensing panel. Local D1 migration 0007
was applied successfully. This is automated verification, not a real browser
login click-through or a production deployment.
