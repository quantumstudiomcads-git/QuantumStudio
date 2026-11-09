# Quantum Studio private production signing service

This step implements an authenticated private issuance/orchestration boundary. It
starts no listener, deploys nothing, provisions no credential/key, and does not open
public website publication endpoints. The response is an immutable **private
persistence result**, not a claim that website publication has completed.

## Boundary and trust model

`operator_tools/licence_manager/signing_service.py` contains a transport-independent
`PrivateSigningService.handle(SigningServiceRequest)` and a small, non-listening
`signing_service_wsgi(service)` adapter for an equivalent private Python runtime.
`signing_service_auth.py` contains caller authentication and durable replay storage.
These modules are private operator code, outside website and desktop packages.

Only explicitly allowlisted trusted backend/operator callers may request issuance.
The only accepted request is HTTPS `POST /v1/licences/issue`, with no query string,
JSON content type and at most 2048 body bytes:

```json
{"schema_version":1,"activation_request_id":"ACTIVATION_UUID"}
```

The UUID shown is an intentionally invalid placeholder. Actual UUIDs must have
canonical lowercase spelling. Duplicate JSON members, extra fields, missing fields,
unsupported versions and malformed identifiers are rejected. The caller cannot send
an account/user, entitlement, device identity, issuer, expiry, limits, nonce inside
a licence, licence payload or signed envelope. The service derives those facts.

The service independently reads the existing bounded authenticated HTTPS operator
activation export via `AuthoritativeWebsiteSource`/`WebsiteActivationsClient`.
That endpoint joins account entitlements by BOTH activation application and user
IDs. The service re-parses the export, rejects missing/duplicate/invalid records,
and selects the activation itself; caller-provided facts are never substituted.
The existing 2000-record/512 KiB export limits remain fail-closed limits, not implicit
pagination or permission to assume records outside the export do not exist.

The public website is authoritative for approval, account entitlement, authorization
and revocation. A compromised authoritative backend is outside this trust model;
key separation prevents private-key exposure but cannot make dishonest authoritative
approval records trustworthy. Issuance credentials must remain narrowly controlled.

## Authentication and freshness

`HmacServiceAuthenticator` implements a service-to-service allowlist with separate
32-byte HMAC-SHA256 shared credentials per caller and per environment. This is NOT a
website bearer token, browser cookie, OAuth token or desktop device proof. TLS is
required independently; MACs do not provide confidentiality.

Headers are:

- `X-QS-Caller`: approved lowercase opaque caller ID.
- `X-QS-Timestamp`: canonical decimal UTC Unix seconds.
- `X-QS-Nonce`: fresh random 32 bytes encoded as 64 lowercase hex characters.
- `Authorization: QS-HMAC-SHA256 <canonical-unpadded-base64url-mac>`.

The MAC covers canonical JSON of exactly: purpose
`quantum-studio:private-licence-issuance:v1`, deployment environment, caller, fixed
method/path, integer timestamp, nonce, and SHA-256 of the exact raw body bytes.
MAC comparison uses `hmac.compare_digest`. The target and method are also enforced
before dispatch. Altering body bytes, caller, nonce, timestamp or environment
invalidates authentication. Unsupported routes/methods cannot reach issuance.

`service_auth_headers` is a private trusted-client helper. Callers must generate a
new cryptographically random nonce for EVERY attempt, including retries after
network errors. Never copy a previously signed request and only change headers.

A valid MAC is accepted only within +/-120 seconds of the service clock. Freshness
is checked again after waiting for serialized issuance. `SqliteRequestJournal`
atomically consumes `(caller, nonce)` before authoritative reads/signing. Claims
are committed independently of issuance and survive failure, process restart and
concurrent calls. Nonces remain until the original signed request cannot still be
fresh. A durable clock high-water mark fails closed on backward clock movement,
including after expiry pruning. Operators must maintain trusted UTC clocks.

The journal must be durable, private and shared by ALL replicas serving a private
issuance database. It serializes the complete read/issue/recheck operation across
processes with SQLite `BEGIN IMMEDIATE`; no in-memory replay cache or mutex is used
as the cross-process safety boundary. SQLite connections are opened per operation,
and the database factory supplies a fresh context-managed operator database handle
per request, supporting concurrent callers without sharing thread-bound connections.
Lock/storage failures fail closed; clients retry with a NEW authenticated nonce.

The journal is tagged with its environment. The existing private database's
`storage_metadata` binds its first service use to environment, authoritative origin
and journal path. Conflicting bindings or TEST trust fail closed. These are public
metadata records, not signing keys or a licence-schema/database migration. Do not
use a fresh independent journal for an already active service, delete replay state,
share staging/production storage, or bypass these bindings during recovery.

## Request flow and reused business logic

1. Enforce transport/method/body limits, authenticate, consume nonce, parse only the
   activation ID, and confirm the running signer/environment remain compatible.
2. Under durable serialization, fetch authoritative activations and validate the
   selected activation using `website_activation_eligibility`.
3. Validate the existing current fixed account entitlement with
   `require_current_entitlement`. Reconcile private original entitlement/envelope
   state against website licence metadata; conflicts fail closed.
4. For new issuance, apply `validate_website_issuance_history`, then call existing
   `issue_website_activation`. The canonical payload and existing fixed grants are
   built there, not in the service or caller.
5. `RuntimeEd25519Signer` signs; the existing independent verification boundary
   verifies the actual payload/signature/device binding before the original envelope,
   original entitlement snapshot, public issuer metadata and audit commit atomically
   in the private database. The authenticated caller maps to a stable opaque audit
   identifier in the existing audit format; raw credentials are never audited.
6. Re-read authoritative state and require the same eligible selected record before
   returning the persistence result. A subsequent publication adapter must still
   enforce the website's own atomic validation and immutable publication rules.

The eligibility/history helpers are extracted from `beta_worker.py` without a new
state machine or policy. The TEST worker delegates to them and otherwise retains
its existing local-only configuration, trust, reconciliation and publication flow.
No entitlement duration, device-limit, revocation, licence format or online access
semantics change. REVOKED activations cannot obtain a response envelope, even when
an old valid signed envelope exists privately. A separately authorized replacement
inherits the original entitlement expiry through the existing builder.

Success is HTTP 200 with `schema_version=1`, result `persisted` or `already_current`,
`envelope_sha256` (existing canonical-envelope digest) and the signed `envelope`.
Only the authenticated backend receives this response. Nothing in the response
contains private keys, authentication credentials or raw provider diagnostics.
Responses use JSON and `Cache-Control: no-store`; the WSGI adapter sets `nosniff`.

## Idempotency, existing state and concurrency limits

A fresh authenticated retry for the same eligible activation recovers the original
verified envelope, ID, nonce, signature and digest. It does not issue another licence
or duplicate issuance audit entries. Exact replay of a consumed service request is
HTTP 409 instead; replay rejection and business idempotency are different layers.
Existing private envelopes are verified through the current immutable recovery path.
Missing original trust, corrupt signatures/bindings, original entitlement changes,
partial/changed remote metadata, or remote metadata without the private original
produce a conflict; the service never invents a replacement envelope to repair them.

Website reads and private persistence are separate transactions. Observed revocation,
expiry, changed facts or an outage during the final read WITHHOLD the envelope. An
already committed private original is preserved for a future eligible fresh retry;
it is never re-signed or automatically deleted. This is not a distributed atomic
commit. Revocation immediately after the final read remains the responsibility of
existing website publication/authorization validation and mandatory desktop online
authorization. No offline authorization is created by this service.

The existing export exposes licence metadata, not a published envelope/digest receipt.
This service compares those facts with its cryptographically verified private
original. It does not claim to have read/verified a separately published website
blob. Production publication and an authenticated publication-receipt/digest adapter
remain a later gate; do not bypass immutable website validation with this result.

## Failure behavior

| Status / safe code | Meaning |
| --- | --- |
| 401 `unauthorized` | Missing/invalid/unapproved caller proof or wrong environment MAC |
| 401 `stale_request` | Expired/future request or freshness elapsed while waiting |
| 409 `replay_rejected` | Authenticated nonce already consumed |
| 400 `malformed_request` | Invalid identifier-only request or headers |
| 403/404/405/413/415 | HTTPS, route, method, size or media-type guard |
| 409 `activation_unavailable` | Missing, unbound, conflicting, unapproved/flagged or revoked activation |
| 409 `entitlement_unavailable` | No currently valid fixed entitlement |
| 409 `licence_conflict` | Existing envelope/history/entitlement/remote metadata mismatch |
| 409 `authoritative_state_changed` | Selected facts changed across the independent reads |
| 503 `source_unavailable` | Authoritative read unavailable/malformed/oversized |
| 503 `configuration_unavailable` | Running signer/environment no longer compatible |
| 503 `issuance_unavailable` / `service_unavailable` | Crypto, private storage/locking/clock or unexpected internal failure |

Error responses contain only `error.code`. Provider/SQL/crypto/configuration exception
strings and raw bodies are neither returned nor logged by the service. Startup
configuration failures produce `ServiceConfigurationError` and no service instance.
The WSGI adapter starts no server and trusts only the hosting server's actual
`wsgi.url_scheme`, never client-supplied `X-Forwarded-Proto`. A future reverse proxy
must authenticate its own forwarding boundary and supply truthful TLS metadata.

## Runtime configuration and secret ownership

All values must be supplied to the PRIVATE signing runtime through approved secure
configuration. `production-signing.env.example` contains blank reference values and
is not an automatic secret loader. No real values have been provisioned.

| Variable | Ownership / purpose | Secret? |
| --- | --- | --- |
| `BETA_ENVIRONMENT` | Explicit `staging` or `production`; all components must match | No |
| `QS_LICENCE_SIGNING_ISSUER_ID` | Existing explicit approved signed `kid` | No |
| `QS_LICENCE_SIGNING_PUBLIC_KEY` | Existing independent public pin | No |
| `QS_LICENCE_SIGNING_KEY` | Existing environment-tagged private Ed25519 runtime record | **YES; signer only, never website** |
| `QS_SIGNING_SERVICE_AUTH` | NEW environment-tagged caller allowlist/credentials below | **YES; complete record signer only** |
| `QS_SIGNING_SERVICE_STATE_PATH` | NEW explicit absolute private SQLite journal path | No key; sensitive operational state/path |
| `QS_OPERATOR_WEBSITE_URL` | Existing explicit approved HTTPS authoritative website origin | No |
| `QS_OPERATOR_SYNC_TOKEN` | Existing read-only operator export credential | **YES; private runtime and existing website verification binding** |

`QS_SIGNING_SERVICE_AUTH` contract:

```json
{
  "schema_version": 1,
  "environment": "production",
  "callers": {
    "APPROVED_CALLER_ID": "APPROVED_CALLER_SECRET_ONLY"
  }
}
```

This placeholder is intentionally invalid. Actual caller IDs match
`[a-z][a-z0-9_-]{0,63}`. Values are canonical unpadded base64url encodings of exactly
32 random secret bytes. The allowlist contains 1-32 callers; duplicate JSON members,
wrong environment, malformed or missing configuration fail closed. Staging uses
its own environment-tagged record and independently provisioned credentials.
Each caller receives ONLY its own HMAC key, never other callers' keys or the full
allowlist. Rotate/remove caller credentials through approved runtime configuration;
keep durable nonce state across rotation/restarts and use a fresh nonce per attempt.
Do not reuse HMAC credentials as operator read credentials or licence signing keys.

`PrivateSigningService.from_environment(database_factory)` composes the real HTTPS
source adapter, runtime signer, authenticator and durable journal. The factory
context manager opens/closes approved EXISTING private operator storage; the service
does not initialize signing-key storage, generate a private signing key, start a
network listener, or select a TEST fallback. Existing local TEST development keeps
using its existing worker; the private deployed-profile service rejects TEST signers.

The desktop may embed only approved public origins and verification trust. It must
never contain a signing-service HMAC key, service credential, private journal or
licence private key. Desktop requests continue through existing device authorization/
licence retrieval/online authorization; the desktop can NEVER invoke this service
using its normal account/session/device credentials.

## What the public website may call

No website call is wired in this step. Later, an explicitly approved website BACKEND
caller may hold its own scoped HMAC credential and request issuance by activation
ID after existing approval/authorization. It cannot supply grants or keys and gains
no direct arbitrary signing API. Browser/frontend code receives no HMAC credential,
service credential or signing key. There is no CORS/session-authenticated browser
signing endpoint, and no new public website route in this change.

## Cloudflare mapping for the next step

The following is a proposed mapping, not deployed configuration:

- Keep public Pages/Functions/D1 separate from the signing runtime. A separate Worker
  can be reachable through an explicitly configured service binding rather than a
  public URL; retain this service's caller authentication/freshness contract at that
  boundary. [Cloudflare service bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/).
- Map request/response transport to a private Worker handler. Supply private signing
  and caller credentials only as that Worker's secret bindings, never public build
  variables or public website signing-key bindings. [Cloudflare secrets](https://developers.cloudflare.com/workers/configuration/secrets/).
- Replace the local SQLite journal with an atomic durable nonce claim and serialized
  issuance coordinator, with one authority scope per environment/database. Durable
  Objects provide private transactional strongly consistent storage; an adapter must
  preserve this implementation's replay and serialization invariants. Process memory
  alone is insufficient. [Durable Objects storage](https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-storage/).
- Preserve the existing issuance, immutable persistence, canonical-signing and public
  verification contracts. Do not assume Python `sqlite3`, DPAPI operator storage or
  `cryptography` runs unchanged in a Worker. A compatible storage/crypto adapter (or
  an equivalent private Python runtime using the supplied WSGI boundary) must pass
  these tests and existing acceptance invariants before deployment.
- Implement authenticated production publication/receipt validation separately,
  retaining the website's own binding, conflict, revocation and immutability gates.

No Wrangler/Cloudflare deployment configuration, public listener, private network,
service binding, secret, Worker, D1 migration or key was created by this work.
Remaining gates include approved key/caller credential provisioning and custody,
private hosting/network/TLS setup, shared durable storage/recovery, production
publication/retrieval adapters, real email delivery, audit-listed auth hardening,
release public trust and a real HTTPS production-style acceptance pilot.


## Selected Cloudflare adapter

The separate Python Worker and SQLite Durable Object adapter is now implemented in
`cloudflare/signing_worker/`. See `CLOUDFLARE_SIGNING_WORKER.md` for its bindings,
secret contract, local dry runs and remaining manual deployment gates. This is the
selected closed-beta hosting path; no VPS or public website change is required.


## Pages Functions Service Binding integration

Pages now calls the private Python Worker through the runtime Service Binding
`SIGNING_SERVICE`. There is no global `fetch` fallback, public Worker URL, browser
binding, licence private key in Pages, or dependency on the final custom DNS name.
The public website remains the authority for activation/entitlement facts; the
Worker independently reloads them through the existing authenticated operator export.

### Trigger and trust boundary

Trusted operator infrastructure explicitly sends:

```http
POST /api/operator/activations/<activation-id>/issue
Authorization: Bearer <OPERATOR_LICENCE_PUBLISH_TOKEN>
Content-Type: application/json

{"schema_version":1}
```

Use the existing purpose-specific publication credential, not a browser session or
operator read token. The endpoint rejects additional fields, including envelopes,
grants, caller identity and activation IDs supplied in the body. The UUID comes
only from the route. HTTPS is required; a supplied Origin must match the configured
website origin. This step does not automatically invoke signing when an activation
is registered, change activation responses, add an issuance UI or alter the local
TEST polling worker. Local calls report `local_worker_required` without needing a
Service Binding. Existing operator metadata/publication routes remain local-only;
the deployed issuance route uses their extracted server-side persistence functions.

### Exact Pages runtime contract

| Binding | Type | Value/responsibility |
| --- | --- | --- |
| `SIGNING_SERVICE` | Service Binding | Matching private signing Worker, e.g. the independently deployed staging Worker; never a public URL |
| `QS_SIGNING_SERVICE_CALLER` | Encrypted Pages secret | One JSON caller record below; NOT a raw key and NOT the Worker allowlist |
| `QS_LICENCE_TRUST` | Public runtime variable | Approved environment-bound licence public trust manifest below; contains no private key |
| `OPERATOR_LICENCE_PUBLISH_TOKEN` | Existing encrypted Pages secret | Authenticates the trusted operator issuance trigger |
| `BETA_ENVIRONMENT` | Existing runtime variable | Explicit staging or production |
| `BETA_ALLOWED_ORIGIN` | Existing runtime variable | Actual current HTTPS website origin |
| `BETA_DB` | Existing D1 binding | Matching environment's authoritative database |

The new encrypted caller record has exactly these members (placeholders below are
format references, not usable credentials):

```json
{"schema_version":1,"environment":"staging","caller":"pages-staging","secret":"CANONICAL_UNPADDED_BASE64URL_32_BYTE_CALLER_SECRET"}
```

The Worker-side `QS_SIGNING_SERVICE_AUTH` remains authoritative:

```json
{"schema_version":1,"environment":"staging","callers":{"pages-staging":"SAME_CANONICAL_UNPADDED_BASE64URL_32_BYTE_CALLER_SECRET"}}
```

`pages-staging` is an example approved caller ID, not hardcoded. Caller IDs must
match `[a-z][a-z0-9_-]{0,63}`. Pages receives only its own credential, never the
complete allowlist or another infrastructure caller's key. If the deployed
allowlist has no dedicated Pages caller, provisioning that caller is manual;
this change does not generate, read, rotate or install credentials. Production
must have a separate caller/secret, environment tag, Worker binding, D1 and trust.

The public trust schema is the existing desktop trust schema, independently
pinned in Pages rather than accepted from the Worker response:

```json
{"schema_version":1,"environment":"staging","domain":"licence","algorithm":"Ed25519","keys":{"lic-APPROVED-LOWERCASE-ISSUER":"APPROVED_BASE64URL_RAW_32_BYTE_PUBLIC_KEY"}}
```

The issuer placeholder is intentionally invalid; use the exact approved `lic-...`
lowercase issuer configured on the matching Worker. Retain historical public
pins during rotation. Never put `QS_LICENCE_SIGNING_KEY` in Pages.

### Request, validation and immutable completion

1. Authenticate the trusted operator trigger; validate the minimal request.
2. Read D1 activation, linked application and matching account entitlement. Require
   AUTHORIZED, no revocation/flag, matching full device hash/installation, an
   approved/licence-issued application and a current beta entitlement. Reject
   inconsistent existing metadata before contacting the Worker.
3. Send only `{"schema_version":1,"activation_request_id":"<uuid>"}` to
   `https://private-signing.internal/v1/licences/issue` THROUGH the binding. The
   hostname is an internal Request target, never resolved by public fetch.
4. HMAC-SHA256 signs the exact Python contract: purpose, environment, caller, POST,
   path, integer timestamp, fresh random 32-byte hex nonce and SHA-256 of the actual
   body bytes, with canonical sorted JSON. The Worker applies its existing
   120-second freshness window, durable replay rejection and serialized issuance.
5. Bound the request and response-body wait to 30 seconds and parse at most 64 KiB
   of JSON. Reject unexpected result schemas, envelope fields, hashes, device/account
   identity, entitlement expiry/limit, issuer or signature. Verify Ed25519 against
   independently configured public trust using the existing canonical envelope.
6. Re-read eligibility after the Worker returns, reject changed entitlement/device
   facts, then reuse shared metadata and immutable publication persistence.
   Publication uses a conditional INSERT that additionally checks current deployed
   authorization, entitlement expiry and device limit. Existing bytes cannot be
   overwritten. Metadata can remain after an interrupted publication; retrying with
   a fresh HMAC nonce recovers the Worker's original envelope and completes storage.

No automatic retries are made across an ambiguous service failure. Operators may
retry with a fresh request; the Worker's durable activation record and website
immutable storage preserve idempotency. Concurrent changes/replay/conflicts fail
closed; no new audit events or licence format are introduced by this adapter.

### Safe failures and rollout limits

Missing binding, caller credential or public trust returns safe configuration
failure. Worker 401/403 returns a safe authentication failure, 409 a safe conflict,
transport/deadline/other status a temporary failure, and malformed/mismatched
responses are rejected. Error bodies from the Worker are never read or forwarded.
No HMAC credential, raw diagnostics, email, private key or envelope is returned in
the operator success response; only publication result and digest are returned.

The desktop cannot invoke the binding or the operator route with its normal
session/device proof. Existing desktop retrieval and online-authorization deployed
TEST-only gates are not opened here; their production readiness is a separate
rollout gate. This implementation proves issuance/publication, not full deployed
desktop acceptance.

### Current staging/manual configuration

Until custom DNS is available, use the already working HTTPS Pages origin
`https://quantumstudio.pages.dev` consistently for `BETA_ALLOWED_ORIGIN` and the
private Worker's `QS_OPERATOR_WEBSITE_URL` (plus matching OAuth/Turnstile settings
as appropriate). Do not use the final staging origin before it resolves and is
configured. No domain is hardcoded in the adapter. When moving domains, coordinate
both origins and existing authentication provider settings manually.

Configure the Pages caller JSON secret and approved `QS_LICENCE_TRUST` public
manifest, confirm the allowlist contains the matching dedicated caller, and review
all changes before deploying this code. A pre-existing Service Binding alone does
not install this integration into an already deployed Pages artifact. No deployment,
remote request, key generation or secret provisioning was performed by this change.
