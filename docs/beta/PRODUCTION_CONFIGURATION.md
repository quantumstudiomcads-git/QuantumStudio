# Quantum Studio deployment configuration

This step adds configuration gates only. The M1-M10 grant, device, revocation,
immutable envelope and mandatory online authorization contracts are unchanged.
It does not enable a production signing authority, production licence metadata/
publication/delivery adapters, or provision a verified email sender. Resend email
transport is implemented separately; its operational contract is documented below. A valid profile is necessary,
but is not approval or readiness to deploy.

## Environment model

`BETA_ENVIRONMENT` is the shared selector for desktop, operator tools, website
build and Pages Functions. Supported values are exactly `local`, `staging`, and
`production`. The existing explicit `test` alias maps to local for compatibility.
Blank, misspelled, differently cased and `development` values are rejected.

| Profile | Local TEST workflow | Origins | Trust and secrets |
| --- | --- | --- | --- |
| local | Explicitly allowed, with existing opt-ins | Existing loopback HTTP exception, or HTTPS | Local TEST trust file; local-only credentials |
| staging | Prohibited | Explicit public HTTPS origin | Explicit staging-tagged public trust; separate staging resources/secrets |
| production | Prohibited | Explicit public HTTPS origin | Explicit production-tagged public trust; separate production resources/secrets |

Python centralizes validation in `backend/licensing/configuration.py`. Website
builds and Functions share `website/functions/_lib/deployment.js`. There are no
network probes, database migrations, or key generation during validation.
An absent Python selector chooses the strict production profile, never local.
An absent website selector is invalid. Neither deployed profile inherits the
local origin, local credentials, or TEST trust.

Configure each process independently. A shell-only static build setting does not
configure deployed Functions. In Pages, configure the matching dashboard environment
so the required values reach both the build process and runtime. `.dev.vars` is a
local Wrangler input, not a release configuration loader. `website/wrangler.toml`
is local-only: it has no `pages_build_output_dir` and no `[vars]` deployment defaults.
Its all-zero D1 identity is only for local tools; real Pages D1 bindings belong to
the dashboard. The existing local helper/package commands supply `build` explicitly.
Use the existing Pages/Functions/D1 architecture; a hosting migration is not
needed for this boundary.

## Desktop configuration

| Variable | Local | Staging / production | Classification |
| --- | --- | --- | --- |
| `BETA_ENVIRONMENT` | Set `local` | Set the exact profile | Public; safe in desktop configuration |
| `QS_WEBSITE_URL` | Existing website origin; optional when not connecting | Required explicit approved HTTPS origin, with no API path | Public; safe in desktop configuration |
| `QS_LICENCE_TRUST` | Not used by the local TEST factory | Required JSON public trust manifest below | Public; safe in desktop configuration |
| `QS_TEST_LICENSING` | Existing TEST workflow requires `1` | Unset or false/0; enabled values rejected | Local switch; never enable in released builds |
| `QS_TEST_LICENCE_TRUST_FILE` | Required existing file for TEST workflow | Must be absent or empty | Public TEST metadata path; not release trust |
| `QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP` | Set `1` for loopback HTTP | Unset or false/0; enabled values rejected | Local switch |
| `QUANTUM_STUDIO_DATA_ROOT` | Existing optional isolated QA root | Existing runtime path policy remains | Machine-specific path; not a credential |

Nonlocal public trust is a single JSON value with **only** these fields:

```json
{
  "schema_version": 1,
  "environment": "production",
  "domain": "licence",
  "algorithm": "Ed25519",
  "keys": {
    "lic-APPROVED_KEY_IDENTIFIER": "APPROVED_CANONICAL_BASE64URL_PUBLIC_KEY"
  }
}
```

This is an intentionally invalid placeholder template. Replace both placeholders
with approved PUBLIC metadata supplied out of band by the future authority.
Actual identifiers must match `lic-[a-z0-9][a-z0-9._-]{0,63}`. Each key must be
canonical unpadded base64url encoding of exactly 32 public-key bytes. Duplicate
JSON members, empty key sets, TEST-domain/key identifiers, wrong algorithms, and
an environment tag different from the selected profile are rejected. For staging,
set the tag to `staging` and use the independent staging authority's public key.
Do not rename or relabel a TEST key as production trust.

The manifest is deployment metadata, not a change to the signed licence schema.
No trust is learned from a website response. Origin and validated trust are
selected at service composition; activation, delivery and online status use that
same origin/HTTP policy. A later process-environment change does not switch a
running service to a local origin.

This step accepts explicit process configuration; it does not package a real
release profile or add an installer secret/configuration store. Normal installed
shortcut provisioning of approved PUBLIC values remains a later release task.
Never solve that task by embedding an operator token or any private key.

## Website build and Functions

| Variable / binding | Local | Staging / production | Classification / exposure |
| --- | --- | --- | --- |
| `BETA_ENVIRONMENT` | `local` | Exact deployed profile, required at build and runtime | Public |
| `BETA_ALLOWED_ORIGIN` | Existing local origin; build defaults to `http://127.0.0.1:8788` only in local mode | Required approved HTTPS root origin at build and runtime | Public |
| `TURNSTILE_SITE_KEY` | Optional for the explicit local test widget | Required at build; hostname-specific real widget key | Public browser configuration |
| `BETA_TURNSTILE_TEST_MODE` | `true` for existing test tokens | Unset/false/0 only | Public switch; never enable for deployed profiles |
| `AUTH_EMAIL_TEST_MODE` | `true` for existing local UI test codes; no OTP logging | Unset/false/0 only | Runtime switch; never enable for deployed profiles |
| `AUTH_EMAIL_PROVIDER` | Not needed; local test/stub provider is retained | Required `resend` for email delivery | Non-secret runtime setting; not public build data |
| `AUTH_EMAIL_FROM` | Not needed | Required approved mailbox at a Resend-verified domain | Non-secret runtime sender; not a build default |
| `RESEND_API_KEY` | Not needed or used | Required separate environment-specific Resend sending credential | SECRET; encrypted Pages runtime binding only |
| `CLOUDFLARE_LOCAL` | Optional existing local indicator | Unset/false/0 only | Local switch |
| `BETA_DB` | Wrangler local D1 binding | Required isolated environment-specific D1 binding | Runtime resource binding; never public build data |
| `BETA_PRIVACY_VERSION`, `BETA_TERMS_VERSION` | Existing draft values | Required actual reviewed document versions | Non-secret runtime configuration |
| `BETA_IDENTITY_PEPPER` | Required local value for applications | Required, non-placeholder independent environment value | SECRET; runtime only |
| `AUTH_OTP_PEPPER` | Existing local value | Required, non-placeholder independent environment value | SECRET; runtime only |
| `TURNSTILE_SECRET_KEY` | Existing local adapter or local verification key | Required real environment-specific verification secret | SECRET; runtime only |
| `OPERATOR_SYNC_TOKEN` | Required when reading applications/activations | Required | SECRET; runtime only |
| `OPERATOR_STATUS_SYNC_TOKEN` | Required when mirroring review status | Required | SECRET; runtime only |
| `OPERATOR_LICENCE_SYNC_TOKEN` | Required for local TEST metadata sync | Required configuration; TEST endpoint still blocked nonlocally | SECRET; runtime only |
| `OPERATOR_LICENCE_PUBLISH_TOKEN` | Required for local TEST publication | Required configuration; production adapter still unavailable | SECRET; runtime only |
| `OPERATOR_ACTIVATION_REVOKE_TOKEN` | Required for operator revocation | Required | SECRET; runtime only |
| `GOOGLE_CLIENT_ID` | Existing optional Google sign-in configuration | Required when Google sign-in is used | Public client identifier; runtime here |
| `GOOGLE_CLIENT_SECRET` | Required when using Google locally | Required when Google sign-in is used | SECRET; runtime only |
| `GOOGLE_REDIRECT_URI` | Existing loopback callback | Required for Google sign-in; selected HTTPS origin plus `/api/auth/google/callback`, no query/fragment/userinfo | Public; runtime configuration |

All five operator tokens are required by the deployed runtime profile, even while
production signing/publication remains disabled. Give each purpose its own
high-entropy credential. Do not reuse credentials between staging and production.
The public build validates only public settings; it neither requires nor emits
runtime secrets. Only the public Turnstile site key and widget mode enter
Docusaurus custom fields. The website build uses root paths for Pages Functions;
the old implicit GitHub Pages URL/subpath fallback has been removed.

Create separate Cloudflare staging/production projects or isolated preview
bindings, D1 databases, encrypted secret bindings, OAuth clients/callbacks and
Turnstile hostname registrations. Configure Pages build variables and runtime
bindings explicitly in each environment. The validator enforces presence and
mode, not external account ownership or whether an operator copied a real secret
between projects. Isolation of actual resources and approval of real values are
manual release checks. Do not put secret values in `wrangler.toml` `[vars]`,
tracked examples, static assets, logs, desktop builds, or command output.

`website/.dev.vars.example` remains local-only. Reference checklists for deployed
profiles are `website/config/staging.env.example` and
`website/config/production.env.example`. They contain blanks deliberately, are not
automatically loaded, and must not be filled with secrets in Git. `.dev.vars`
and all suffixed local-secret variants are ignored, except the committed example.

## Cloudflare Pages dashboard ownership

Pages can read tracked Wrangler variables into its build/deployment configuration.
Previously `pages_build_output_dir` opted `website/wrangler.toml` into that role,
so top-level production mode and a placeholder origin overrode the intended staging
settings. Removing `[vars]` alone would leave a deployed Wrangler configuration
managing bindings. The file now omits that deployment opt-in entirely; it remains
usable by `wrangler pages dev build` and `d1:migrate:local`.

Cloudflare documents the no-output-directory local-only mode and Wrangler's source
of truth behavior in [Pages Wrangler configuration](https://developers.cloudflare.com/pages/functions/wrangler-configuration/).
Do not reintroduce `pages_build_output_dir` or deploy-time `[vars]` without explicitly
changing this dashboard-managed deployment model. No validator was relaxed.

In the Pages project dashboard set root directory `website`, build command
`npm run build`, and build output directory `build` (relative to that root).
Configure the Functions compatibility date separately to the reviewed local value
`2026-09-20`; the local-only Wrangler file no longer supplies remote settings.

Choose the actual Pages deployment slot, not just the name of the branch:

- A dedicated staging Pages project's **Production** slot can and should have
  `BETA_ENVIRONMENT=staging` when its production branch is `production-beta-v0.2`.
- A branch preview on a shared Pages project uses that project's **Preview** slot.
- The actual production site's Production slot uses `BETA_ENVIRONMENT=production`.

The application never infers deployment mode from branch names, `CF_PAGES_URL`, or
Pages' Production/Preview label. Set each environment explicitly. Replace any
previously saved production/placeholder values in that slot; do not assume removing
them from Git edits existing account settings. Dashboard variables apply at build
and runtime; verify the selected environment in both views after configuration.
[Pages environment variables](https://developers.cloudflare.com/pages/functions/bindings/#environment-variables).

For STAGING set the following public values manually, without putting real hosts
or identifiers into tracked defaults:

| Name | Dashboard value |
| --- | --- |
| `BETA_ENVIRONMENT` | `staging` |
| `BETA_ALLOWED_ORIGIN` | The approved staging HTTPS origin, root only; no path |
| `TURNSTILE_SITE_KEY` | Real public staging widget key registered for that hostname |
| `BETA_TURNSTILE_TEST_MODE` | `false` |
| `AUTH_EMAIL_TEST_MODE` | `false` |
| `CLOUDFLARE_LOCAL` | `false` or absent |
| `BETA_PRIVACY_VERSION` | The actual staging privacy document version |
| `BETA_TERMS_VERSION` | The actual staging beta terms version |

The first three values plus disabled TEST flags are necessary for a valid static
build. For a usable Functions runtime also configure encrypted staging secret
bindings `AUTH_OTP_PEPPER`, `BETA_IDENTITY_PEPPER`, `TURNSTILE_SECRET_KEY`,
`OPERATOR_SYNC_TOKEN`, `OPERATOR_STATUS_SYNC_TOKEN`, `OPERATOR_LICENCE_SYNC_TOKEN`,
`OPERATOR_LICENCE_PUBLISH_TOKEN`, and `OPERATOR_ACTIVATION_REVOKE_TOKEN`.
Use independent non-placeholder staging values and purpose-specific credentials.
Bind `BETA_DB` to the real staging D1 database in the same Pages deployment slot;
the reviewed existing migrations must be present. `BETA_DB` is a resource binding,
not a plaintext environment variable or the local all-zero database ID.

If using Google sign-in, set `GOOGLE_CLIENT_ID`, encrypted `GOOGLE_CLIENT_SECRET`,
and `GOOGLE_REDIRECT_URI=<STAGING_HTTPS_ORIGIN>/api/auth/google/callback`, and register
that exact callback externally. Keep `QS_TEST_LICENSING`, local HTTP exceptions and
TEST trust files absent; staging uses production-style gates. Never add a private
licence signing key or signing-service caller allowlist to Pages. Production uses
the same variable names with independently approved production values and secrets.

Local development still uses `.dev.vars`, local D1 and `scripts/qs-local.ps1`.
Nothing automatically loads `website/config/*.env.example`. Missing deployed mode,
origin, public widget key or runtime bindings remain failures rather than local
fallbacks. The Pages configuration fix does not provision Resend credentials,
verify sender DNS, enable the deferred licence adapters or perform a deployment.

## Transactional email through Resend

Email delivery requires `AUTH_EMAIL_PROVIDER=resend`, `AUTH_EMAIL_FROM` and encrypted
`RESEND_API_KEY` in the matching Pages runtime environment. These are NOT static build
inputs and are not Docusaurus custom fields. Staging/production require their own
credentials and approved senders; `AUTH_EMAIL_TEST_MODE=true` remains prohibited.
Local mode keeps its existing `devOtp` UI workflow without network requests or OTP
console logging, including the existing explicit-local stub behavior.

Configuration is checked when email is requested. Public builds and unrelated
routes, including configured Google OAuth, do not require or receive the API key.
Invalid/missing email settings return the existing safe 503 verification-delivery
failure; they never downgrade staging/production to local test email. No OTP
lifetime, generation, throttling or consumption semantics change.

As of this step, `quantumstudio-mcads.com` still awaits DNS access/verification.
Do not add a usable API key or attempt real sending before the exact sender domain
is verified in Resend. Leave `RESEND_API_KEY` unconfigured while blocked: email
requests then fail locally at configuration validation without a provider call.
After verification, a manual example (NOT an application default) is:

```dotenv
AUTH_EMAIL_PROVIDER=resend
AUTH_EMAIL_FROM="Quantum Studio <no-reply@quantumstudio-mcads.com>"
AUTH_EMAIL_TEST_MODE=false
```

Add `RESEND_API_KEY` as an encrypted Pages secret with an independently provisioned
sending-scoped key for that environment. The example mailbox still needs approval;
a verified staging subdomain can be used instead, after separate domain verification.
The website origin and the email sender's verified domain are different settings.
See `PRODUCTION_EMAIL_DELIVERY.md` for the adapter, failure behavior and manual DNS
steps. No real API key, DNS change, deployment or email send was performed here.

## Operator processes and local helpers

Licence Manager startup uses the same Python selector/switch/origin validation.
`--test-mode` is allowed only in local mode. Nonlocal startup requires an explicit
approved `QS_OPERATOR_WEBSITE_URL` HTTPS origin. Its existing purpose-specific
credentials remain `QS_OPERATOR_SYNC_TOKEN`, `QS_OPERATOR_STATUS_SYNC_TOKEN`,
`QS_OPERATOR_LICENCE_SYNC_TOKEN`, `QS_OPERATOR_LICENCE_PUBLISH_TOKEN`, and
`QS_OPERATOR_ACTIVATION_REVOKE_TOKEN`; each must match its corresponding website
binding. They are secrets on the private operator host, never desktop/browser
configuration. Existing per-operation missing-credential checks remain in force.
No production signing key or authority is created by selecting a profile.

`beta_worker.py` remains the existing explicitly local TEST worker, unavailable
in staging/production. `scripts/qs-local.ps1` explicitly selects local before
starting website/build, desktop, Licence Manager and TEST worker workflows.
The desktop helper still sets the existing TEST trust-file and HTTP opt-ins.
Do not source the local helper in a deployment shell. For standalone local
commands, explicitly set `BETA_ENVIRONMENT=local` first. Existing isolated device
roots, TEST ephemeral signing, and local regression fixtures are preserved.

## Prohibited deployed settings and failure behavior

Both staging and production reject enabled TEST licensing, TEST trust files,
local HTTP exceptions, local email/Turnstile modes, and `CLOUDFLARE_LOCAL`.
Invalid flag spellings fail rather than being treated as false. Origins must be
HTTPS root origins without credentials/query/fragment. Loopback/IP literals,
localhost/local domains, reserved example/test/invalid domains, and obvious
replace-with/placeholder URLs are rejected. Known all-zero dummy Turnstile key
patterns and placeholder secret values are rejected even when test mode is off.
This is syntactic configuration validation, not DNS or secret-authenticity proof.

- Desktop invalid/missing deployed configuration produces an unavailable service
  (`configuration_invalid`) before protected storage/identity creation or network
  use. The account dialog reports configuration unavailable. Read-only application
  use can continue under existing policy; protected work receives no grant.
- Website invalid build configuration throws a safe configuration error before
  producing the public site. Invalid runtime configuration returns HTTP 503 with
  `configuration_unavailable` before routing, with no token/body/config values.
  Valid staging/production profiles also reject inbound HTTP before routing.
- Google sign-in separately rejects missing credentials, placeholder credentials,
  or a callback that does not match the chosen deployed origin and callback path.
- Staging and production cookies use `Secure`. Neither can return/log local OTPs
  or succeed through the stub email adapter. Resend delivery is available only with
  explicit valid email configuration; missing settings fail the email operation closed.
- Existing TEST metadata/publication/retrieval adapters stay closed outside local;
  selecting a valid production profile does not bypass their TEST-only guards.
- Operator startup rejects incompatible configuration before constructing the
  window or signing authority. Existing worker guards continue to reject nonlocal
  TEST work. No automatic environment downgrade or retry through local defaults.

The website must never possess the licence private signing key. Device identity
keys remain separately protected by the existing OS mechanism. Production licence,
updater, installer-signing and operator credentials are different responsibilities.

## Remaining release blockers

The production-readiness audit remains authoritative for work beyond this step:
persistent production signing/custody, explicit production metadata/publication/
delivery adapters, verified Resend sender/DNS and scoped credentials, OTP/OAuth security hardening, approved
public copy/consent, actual external resource configuration, desktop public-profile
provisioning, installer/release validation and a real HTTPS acceptance pilot.
No keys, domains, credentials, resources or deployments were provisioned here.


## Private signing runtime follow-up

The separately implemented signing contract is documented in
`PRODUCTION_SIGNING_AUTHORITY.md`: `QS_LICENCE_SIGNING_ISSUER_ID`,
`QS_LICENCE_SIGNING_PUBLIC_KEY`, and secret `QS_LICENCE_SIGNING_KEY` belong only
to the private signing runtime. They are not website bindings or desktop build
settings. The implementation does not provision keys or enable production website
publication; key custody, private orchestration and deployment remain blocked.


## Pages issuance integration follow-up

Pages Functions now have a server-only `SIGNING_SERVICE` client and authenticated
`POST /api/operator/activations/<activation-id>/issue` trigger. The body is exactly
`{"schema_version":1}` and the trigger requires the existing
`OPERATOR_LICENCE_PUBLISH_TOKEN`. Local TEST issuance remains unchanged.

Required additional Pages runtime configuration:

- `SIGNING_SERVICE`: Service Binding to the matching private Worker.
- `QS_SIGNING_SERVICE_CALLER`: encrypted JSON secret with exactly `schema_version:1`,
  matching `environment`, approved `caller` and `secret` (canonical unpadded base64url
  of 32 bytes). This is NOT a raw key. Worker `QS_SIGNING_SERVICE_AUTH.callers[caller]`
  must contain the same secret; the Worker allowlist remains authoritative.
- `QS_LICENCE_TRUST`: public JSON manifest with `schema_version:1`, matching
  `environment`, `domain:"licence"`, `algorithm:"Ed25519"` and `keys` mapping approved
  `lic-...` issuer IDs to canonical base64url raw 32-byte public keys. Never supply
  private signing keys to Pages.

Use independent staging/production callers, secrets, trust, D1 and bindings. These
settings are runtime-only, not public build configuration. Missing/invalid settings
fail the issuance operation closed without changing unrelated page/auth behavior.

Pages verifies the HMAC-compatible response envelope's Ed25519 signature against
pinned trust and matches authoritative entitlement/device facts before reusing shared
metadata and immutable publication persistence. Worker replay/freshness/serialization
remain authoritative; retries use fresh nonces and recover the original envelope.
No automatic activation side effect or desktop direct binding access was added.

While DNS is pending, the working HTTPS Pages origin can be used consistently for
Pages `BETA_ALLOWED_ORIGIN` and Worker `QS_OPERATOR_WEBSITE_URL`. Final custom DNS is
not required for Service Binding calls. Existing desktop deployed TEST-only gates
remain a separate acceptance blocker. No deployment or secret provisioning occurred.

See [the full Pages runtime contract and flow](PRODUCTION_SIGNING_SERVICE.md#pages-functions-service-binding-integration)
for exact JSON formats, authentication, failure behavior and manual rollout steps.


## Web admin console

`/admin` now provides server-guarded website licence management. Set runtime-only
`QS_ADMIN_ENABLED=true` and `QS_ADMIN_USER_IDS` to a JSON array of independently
approved existing verified user UUIDs to enable it. Default examples leave admin
OFF. No email/domain or first-user promotion is supported. The allowlist must not
be passed to Docusaurus public configuration. Unconfigured/invalid admin access
fails closed without blocking public pages or the existing local TEST workflow.

Every admin operation uses the existing HttpOnly session plus the server-managed
allowlist. Mutations require same-origin JSON/custom-header checks. Review and
revocation reuse existing operator handlers; issuance calls the existing private
Service Binding implementation. Operator tokens and signing credentials remain
server-only. Existing authentication hardening requirements still apply; keep
admin disabled if stronger operator authentication is required by deployment policy.
See [Web Admin Licence Manager](WEB_ADMIN_LICENCE_MANAGER.md) for the audit, exact
routes, workflow, configuration and staging acceptance requirements.
