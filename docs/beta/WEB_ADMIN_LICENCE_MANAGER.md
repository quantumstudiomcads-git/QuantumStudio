# Web Admin Licence Manager

## Existing architecture audit

Before this change, no admin page or administrator role/allowlist existed. Public
account pages used the existing server-validated `qs_session` HttpOnly cookie;
normal sessions were not permission to perform operator actions. Sessions contain
a random token whose hash is stored in D1, are revocable and expire. Staging and
production cookies already use Secure and SameSite=Lax. This change neither replaces
login nor changes OTP, OAuth or session lifetime semantics.

Existing operator routes use distinct server-side bearer credentials:

- `GET /api/operator/applications` and `/api/operator/activations`: private exports.
- `GET/POST /api/operator/applications/{id}/status`: guarded review transitions,
  expected-state concurrency checks, audit and approval entitlement provisioning.
- `POST /api/operator/activations/{id}/issue`: deployed identifier-only issuance
  through the private Service Binding.
- `POST /api/operator/activations/{id}/revoke`: terminal device revocation and audit.
- Metadata `/licence` and envelope `/publish`: existing local TEST-facing routes;
  deployed issuance reuses shared server-side persistence rather than opening them.

`Start-QSLicenceManager` exposes local import/sync, review, TEST issuance, metadata
sync, publication/export, device revocation, maintenance/audit and signing status.
The web console provides the corresponding core website operations: authoritative
application/user/entitlement/device/licence inspection, review, private-service
issuance, device revocation and explicit refresh. It does not reproduce private
key management, TEST trust export, local file import/export or local maintenance.
Those local tools and the separate private signing Worker are untouched.

## Default-deny authorization and configuration

No sufficient admin authorization existed previously. The new guard uses the
existing session mechanism PLUS an independently configured immutable user-ID
allowlist. It is disabled by default, has no first-user bootstrap, no public
promotion endpoint, no email/domain-based promotion and no bearer-token login UI.
Normal signup or a verified session alone never grants administrator access.

Pages runtime variables (not static build/public settings):

```text
QS_ADMIN_ENABLED=false
QS_ADMIN_USER_IDS=
```

After independently verifying the intended operator identity, an authorized
Cloudflare administrator can explicitly set:

```text
QS_ADMIN_ENABLED=true
QS_ADMIN_USER_IDS=["<approved-canonical-user-uuid>"]
```

The second value is a JSON array with 1-20 unique canonical lowercase UUIDs,
not emails. The placeholder above is deliberately invalid. Select existing verified
D1 users by an independent trusted process; never add an applicant because they
requested operator access. The allowlist is not a cryptographic secret, but is
private operational configuration and must stay out of public bundles.
Use separate staging/production account approvals and runtime configuration.
Removal from the allowlist, disabling admin or session revocation denies future
requests. Accounts must remain VERIFIED with a valid verification timestamp.

The guard additionally requires an explicit deployed environment, valid existing
runtime configuration, matching HTTPS website origin and a live unrevoked session
with finite expiry. Local/test environments cannot enable the web console; use
local Licence Manager tooling there. Unset/invalid admin configuration denies all
admin access without affecting public/auth/licensing routes.

This is session authentication plus server-managed administrator authorization,
not a new MFA/Cloudflare Access identity system. Existing login security limitations
and production hardening requirements still apply. If deployment policy requires
stronger operator authentication, keep `QS_ADMIN_ENABLED=false` until that mechanism
is completed. No external authentication, allowlist or secret was provisioned here.

## Routes and operator workflow

- `/admin`: no-index master/detail console. No public navigation/homepage change.
- `GET /api/admin/applications?offset=0`: bounded summaries, 100 per page.
- `GET /api/admin/applications/{applicationId}`: linked user, entitlement and up to
  200 activation/licence summaries, including public issuer where published.
- `POST /api/admin/applications/{applicationId}/action`: authenticated actions.

Every API handler independently checks admin authorization. The root middleware
also protects admin page aliases and prevents caching/framing/indexing. Public
static assets contain only the generic UI shell/code; they contain no applicant
records, account grants, allowlist or privileged credentials.

Sign in using the existing website login, then navigate directly to `/admin`.
Select an application from the table. There is no free-form activation ID or
licence payload input. The detail panel shows applicant/user IDs, contact/institution,
review status/date, entitlement plan/start/expiry/limit/revision, devices, flags,
licence metadata, publication state and issuer.

- Begin review follows APPLIED -> UNDER_REVIEW. Approve/reject are available only
  from UNDER_REVIEW. Rejection asks for confirmation. No intermediate state is
  skipped; the existing expected-state guard rejects stale decisions.
- Issue Licence is available only for a currently entitled eligible authorized
  device. It calls the existing `issueLicenceViaService`, also used by the operator
  `/issue` endpoint. D1 eligibility, fresh HMAC request, Worker authoritative read,
  durable replay/serialization, signature verification and immutable metadata/
  publication remain in the existing implementation. The browser never holds the
  publication bearer token or signs a service request.
- Success returns freshly read licence ID, timestamps, device association and
  publication/issuer summaries. A retry recovers the existing immutable licence.
- Revoke Device requires an explicit confirmation and an existing reason code,
  then invokes the existing server-side operator revocation handler. It leaves
  entitlement expiry, device-limit rules and signed bytes unchanged. Device
  authorization REVOKED is displayed separately from historical signed licence
  metadata; null historical licence_revoked_at is not fabricated into a new event.
- Refresh explicitly re-reads D1. There is no interval polling. Errors clear stale
  selected details and prompt refresh before a subsequent action.

## Browser/server security boundary

Mutations require the live admin session, matching Origin, JSON and the custom
`X-QuantumStudio-Admin: 1` header. Cross-site fetches are denied; no CORS permission
is added. These checks complement SameSite cookies and prevent cross-origin forms
or scripts from exercising privileged actions. Request/action fields are bounded
and exact; activation actions verify membership in the selected application's user
and reject arbitrary envelopes/grants. The signing implementation still independently
rejects revoked, expired or otherwise ineligible activations.

Only server-side orchestration constructs internal Requests for the existing review
and revocation handlers using runtime credentials. No internal bearer, HMAC record,
private key, token hash, raw envelope or provider diagnostics are serialized into
admin responses. The client ignores failure bodies and renders only fixed safe
messages. React renders applicant text as text, without HTML injection.
API/page responses are private/no-store, no-index and frame-denied. Admin query
limits bound result sizes; no new database migration or state machine was added.
Existing operator audit semantics are retained; the console does not introduce a
new per-human audit schema. The private signer sees the approved Pages service
caller, not a browser identity.

## Validation and remaining staging work

Tests use actual SQLite migrations/sessions and the real Pages issuance implementation
with a mocked Service Binding and known synthetic signing fixture material. Rendered
React detail tests exercise returned licence state; these are not browser click-through
or live staging verification. Network-disabled builds scan every static artifact for
all operator/signing/OAuth/email secret names and synthetic canary values, including
the private allowlist. No actual credentials or production/staging signing keys are
read, generated, written or sent by these tests.

Before deployment, independently approve the operator user ID, review the existing
login authentication posture, configure the two admin variables and confirm the
already documented Pages signing caller/public trust/binding and operator action
credentials. Keep admin disabled until those checks and any required stronger
identity controls are complete. Use the currently working HTTPS staging Pages
origin consistently while custom DNS is pending. After an authorized deployment,
perform real sign-in, review, issuance/retry and device-revocation acceptance with
controlled staging records. Deployed desktop TEST-only gates remain separate work.
This change performs no deployment, provisioning, real signing request or email send.
