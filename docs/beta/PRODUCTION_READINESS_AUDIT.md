# Quantum Studio v0.2 closed-beta production-readiness audit

Date: 2026-11-07. Branch: `production-beta-v0.2`. Inspected HEAD: `95e089c`.
The working tree was clean at audit start. This is an audit, not implementation or deployment approval.

## Verdict and scope

**SECURITY BLOCKER ? the current checkout is not ready for real production onboarding.**
M1-M10 is a known-good LOCAL TEST baseline. Production signing/trust, delivery adapters,
email, and deployment configuration are deliberately incomplete. Recorded local tests
are not evidence that these production boundaries work.

**READY ? retain the existing Cloudflare website architecture. No hosting/database migration is necessary.**
Docusaurus assets on Pages, JavaScript APIs on Pages Functions, and D1 fit this closed
beta. Keep the persistent licence signer on a separately controlled operator host.
Pages supports D1 bindings and encrypted secrets, and Workers supports Ed25519
verification: [Pages bindings](https://developers.cloudflare.com/pages/functions/bindings/),
[Pages configuration](https://developers.cloudflare.com/pages/functions/wrangler-configuration/),
[Web Crypto](https://developers.cloudflare.com/workers/runtime-apis/web-crypto/).
Production adapters/configuration are needed, not replacement of the state machines.
A possible future preference for Workers hosting is not a migration requirement here.

Classifications used for every finding:

- **READY**: inspected control/design can be retained; not a live-deployment certification.
- **CONFIGURATION REQUIRED**: external resource, credential, binding, operational decision or validation is needed.
- **CODE CHANGE REQUIRED**: focused source/config-file changes are necessary for the intended production flow.
- **SECURITY BLOCKER**: do not expose the affected production path until the stated prerequisite is satisfied.
- **OPTIONAL**: improvement not required for a properly controlled minimal Windows closed beta.

No source code, migrations, local secrets, keys or deployed resources were changed.
Only this report was created. No tests, builds, migrations, GUI launches, signing-key
generation or authenticated remote-account probes were run. Public vendor documentation
was consulted. Cloudflare/Google/GitHub account settings remain unverified.

## Website, Pages, and D1 findings

| ID | Classification | Evidence and required action |
| --- | --- | --- |
| W01 | READY | Existing Pages/Functions/D1 architecture is suitable. The website stores public licence artifacts/metadata and verifies device proofs. It must never possess the production licence private key, including via Pages secrets or D1. |
| W02 | CODE CHANGE REQUIRED | `website/docusaurus.config.ts:14-23` selects `https://kalapatapubhargava.github.io` and `/QuantumStudio-Website/` whenever CLOUDFLARE_LOCAL is not true. Root-relative browser APIs/callbacks conflict with that GitHub Pages subpath. Configure the approved production HTTPS origin and baseUrl `/`, retaining the explicit local profile. Enabling CLOUDFLARE_LOCAL in production is not a fix. |
| W03 | CONFIGURATION REQUIRED | Identify/create the Pages project, select production branch `production-beta-v0.2`, build root `website`, command `npm run build`, output `build`, and a Node version compatible with package.json (`>=20`). Configure the approved HTTPS domain and deploy the Functions tree as well as assets. package.json's `deploy` is Docusaurus deploy, not a Pages deployment procedure. No website deployment workflow is present; dashboard Git integration is sufficient. |
| W04 | CONFIGURATION REQUIRED | `website/wrangler.toml` still has an all-zero database ID and placeholder origin. Create/bind the real D1 database as BETA_DB and set the canonical origin. Use separate preview/staging databases and secrets; never point previews at production researcher data. No remote binding/project was queried. |
| W05 | READY | The 12 ordered migrations retain the established model. 0009 enforces fixed 7,776,000-second beta grants and default limit 1; 0010 preserves activation/publication/challenge history and installs approval provisioning; 0011 makes REVOKED terminal; 0012 adds state revisions and separate status challenges. No schema rewrite or new production migration is justified by this audit. |
| W06 | CONFIGURATION REQUIRED | Rehearse and then apply 0001 through latest to a fresh production D1 database under explicit operational approval. Before upgrading an existing database, inventory its migration ledger and verify export/backup/restore, particularly 0010's copy/rebuild. Do not import TEST accounts, sessions, entitlements, envelopes or trust into production. Legacy grants must not acquire invented 90-day terms. Prior M10 evidence is documented; migration tests were not rerun here. |
| W07 | CONFIGURATION REQUIRED | Assign Cloudflare/D1 ownership, least-privilege access, backup/recovery, retention, quota and availability monitoring. Names/emails/institutions remain sensitive data; email_lookup_hash does not mean all PII is anonymized. Outage must continue denying new protected work without offline grace. |
| W08 | CODE CHANGE REQUIRED | `website/src/components/ProfessorPages.tsx` contains draft privacy/terms, a `.example` contact, local-preview language and a statement that temporary licences are not issued automatically. Obtain approved text/contact/consent versions and accurately describe manual approval followed by authorized-device issuance. Match BETA_PRIVACY_VERSION/BETA_TERMS_VERSION to the approved copy. This is not a legal-compliance certification or a change to approval policy. |

## Signing, worker, delivery and desktop trust findings

| ID | Classification | Evidence and required action |
| --- | --- | --- |
| L01 | SECURITY BLOCKER | `operator_tools/licence_manager/beta_worker.py` requires explicit local/test mode, loopback URL and TestEphemeralAuthority; main creates a new ephemeral signer. `issuance.py::issue_website_activation_for_testing` rejects production authorities. Saving the TEST private key is not a production solution. A persistent, separately held production authority must be integrated with website-activation issuance. |
| L02 | READY | `signing.py` already provides a ProductionAuthority skeleton and CurrentUser-DPAPI key format. It limits key use to internally authorized issuance, checks public metadata, and refuses automatic key replacement. Production kids use `lic-...`; TEST kids use `test-lic-...`. This is reusable groundwork, not evidence that a real production authority is provisioned or operationally tested. |
| L03 | SECURITY BLOCKER | Approve production key custody/provisioning, restricted operator access, audit, backup/recovery and restart/rotation before real issuance. DPAPI blobs are user/machine-context-bound; copying a blob alone is not verified disaster recovery. This audit did not inspect protected-key files or create keys. Licence private material must stay off the website, CI/customer builds and researcher machines; keep licence/update/installer keys separate. |
| L04 | CODE CHANGE REQUIRED | Existing ProductionAuthority.issue() calls the legacy local activation-request workflow, which builds `now +90 days` envelopes and advances local application state. It is not a drop-in M8/M9A website-activation signer. Add a narrow bridge in `signing.py`, `issuance.py`, `beta_worker.py` using the same authorized website facts, original fixed entitlement expiry and grants, protected signer, audit and idempotent recovery. Reuse `entitlements.py`; do not reset the term or expose generic arbitrary-payload signing. |
| L05 | CODE CHANGE REQUIRED | `operator_tools/licence_manager/licence_delivery.py` recovers only test-licence metadata/test-lic kids and requires test_mode for publication. `website_sync.py::WebsiteLicenceMetadataClient` also requires test_mode. Add explicit production adapters with the same binding/retry contracts; preserve current TEST restrictions. |
| L06 | CODE CHANGE REQUIRED | `website/functions/api/operator/activations/[activationId]/licence.js:35` returns test_only in production. `_lib/licence-delivery.js::gate` blocks publication AND delivery challenge/retrieval outside local/test, and validEnvelope accepts only TEST kids. Production is blocked even with correct environment settings. Add explicit HTTPS production branches and controlled production issuer IDs/public metadata while preserving authentication, authorization, immutable bytes and single-use proofs. If publication verifies issuer signatures, it uses PUBLIC keys only. The website never signs. |
| L07 | SECURITY BLOCKER | `backend/licensing/service.py::production()` injects `trusted_public_keys={}`. Every production envelope will be rejected. Supply a release-controlled production PUBLIC trust set matching the separate authority, with strict licence/update/TEST domain separation. No private key belongs in the desktop. |
| L08 | SECURITY BLOCKER | `backend/licensing/local_test_trust.py::configured_licensing_service()` accepts QS_TEST_LICENSING=1 and a local TEST trust file without a shipping-build/profile boundary. A public beta must not require customers to enable TEST trust. Introduce a production release profile selecting production origin/trust and refusing TEST/local-HTTP overrides; preserve explicitly separate LOCAL TEST workflows. This is a shipped trust-boundary requirement, not a claim of preventing arbitrary executable modification. |
| L09 | CODE CHANGE REQUIRED | `frontend/app/account_dialog.py` and `backend/licensing/online_authorization.py` look up QS_WEBSITE_URL with no usable default. Normal installed shortcuts do not inherit the QA shell setup. Supply the approved HTTPS origin through release-controlled public configuration and use it consistently with production trust. Existing connectors already enforce HTTPS except explicit QA loopback and reject redirects; reuse them. |
| L10 | READY | Device-status and desktop-auth libraries, operator read/status/revoke endpoints and HTTPS connectors have reusable production-compatible checks. Preserve signed/device binding, separate proof domains, single-use challenges, durable revocation, entitlement/revision checks and can_start_protected_work. Cached success must never become an offline grant. |
| L11 | CONFIGURATION REQUIRED | Choose a restricted, operational Windows operator host/user and preserve its database/audit state. Licence Manager review/revocation can remain. Manual website licence buttons are TEST-only; enabling them is unnecessary if a properly integrated production worker handles issuance/publication. Do not use the local helper as a production worker runbook. |

## Authentication findings

| ID | Classification | Evidence and required action |
| --- | --- | --- |
| A01 | CODE CHANGE REQUIRED | `_lib/email-delivery.js` explicitly fails in production and has no real provider adapter. Advertised signup/login/resend OTP cannot work by configuration alone. Implement provider transport and configure sender/domain/credential. Google-only onboarding could defer email only with an explicit decision and safely disabled/unadvertised OTP paths; that is not the present UX. |
| A02 | SECURITY BLOCKER | `_lib/auth.js::issueChallengeForUser` uses Math.random() for OTPs. verifyOtpChallenge reads attempt_count/used_at and separately increments/marks used without conditional consumption. Concurrent requests can pass stale checks. Use cryptographically secure unbiased generation and atomic attempt/expiry/single-use guards before exposing real OTP auth. Keep hashing and existing limits. This is source analysis, not an executed attack. |
| A03 | SECURITY BLOCKER | Google state is random, hashed in D1 and uses PKCE, but `_lib/google-auth.js` / `api/auth/google/start.js` do not bind it to the initiating browser. callback/complete/pending treat a URL/body state as a bearer and perform non-atomic used_at operations. Bind both login and pending signup to the browser and consume state atomically before creating an authenticated result. Exact files: `_lib/google-auth.js`, `api/auth/google/{start,callback,pending,complete}.js`. Login-CSRF/replay/concurrent completion is a source finding, not a reproduced exploit. |
| A04 | CONFIGURATION REQUIRED | Create/verify a Google Web OAuth client, consent/branding and invited-user audience/access. Configure exact `https://<approved-host>/api/auth/google/callback`, authorized origin and matching GOOGLE_REDIRECT_URI/client credentials; isolate staging. Local credential presence does not establish Cloud Console correctness. GOOGLE_CLIENT_SECRET must not enter frontend customFields. |
| A05 | OPTIONAL | resolveGoogleUser decodes an ID token received directly from Google's fixed HTTPS token endpoint and checks issuer/audience/expiry/verified email/subject, without independent JWT signature verification. Google permits relying on the authenticated direct HTTPS exchange in this server flow, so lack of a separate JWKS check alone is NOT a confirmed bypass here. Independent signature/nonce verification is defense in depth; it becomes mandatory if a future path accepts externally supplied ID tokens. A03 remains a separate blocker. |
| A06 | CONFIGURATION REQUIRED | Existing Turnstile validation checks hostname and expected action (auth_otp/beta_registration). Configure the real widget/hostnames, PUBLIC build-time TURNSTILE_SITE_KEY and runtime-secret TURNSTILE_SECRET_KEY. Rebuild with BETA_TURNSTILE_TEST_MODE=false and disable both test flags in Functions; verify real-hostname/action behavior in an authorized staging smoke. |
| A07 | SECURITY BLOCKER | Exact BETA_ENVIRONMENT=production is essential. Current auth treats missing/other values as non-production; email-delivery's generic non-production stub can return devOtp and cookies are Secure only in production. Fail closed on unknown deployment modes/configuration, restrict stub/test behavior to explicit LOCAL TEST and validate production HTTPS/origin. Required boundaries: `_lib/auth.js`, `email-delivery.js`, `beta-registration.js`, `google-auth.js` runtime validation. Preserve explicit local/test behavior. |
| A08 | READY | Session tokens are randomized and hashed in D1; correctly configured production cookies are HttpOnly/SameSite=Lax/Secure. Operator bearer credentials are separated by privilege. Desktop device proof needs no browser cookies or operator credential. Retain these controls while fixing the distinct A02/A03 consumption gaps. |
| A09 | OPTIONAL | Pilot aggregate IP quotas for researchers behind a shared university NAT. Device-status/delivery quotas are bounded but shared by IP. Calibrate only if measured usage requires it; improve rate-limit messaging rather than treating failure as AUTHORIZED or adding polling/grace. Relevant files: `_lib/device-status.js`, `_lib/licence-delivery.js`, Python connectors/device_status.py. |

Google's [OpenID Connect guidance](https://developers.google.com/identity/openid-connect/openid-connect)
requires anti-forgery state to match the initiating client/session and distinguishes
direct authenticated HTTPS token exchange from accepting browser-supplied ID tokens.

## Secrets, Git tracking, and operator configuration findings

| ID | Classification | Evidence and required action |
| --- | --- | --- |
| S01 | READY | Local website/.dev.vars exists, is ignored and NOT tracked. Locally available `git log --all` showed no commits touching that path; only `.dev.vars.example` is tracked. The audit inspected names/presence with values masked. This local file is not proof of deployed credentials. |
| S02 | CODE CHANGE REQUIRED | `.gitignore` / `website/.gitignore` ignore `.env*` and exact `.dev.vars`, but the exact rule does not cover `.dev.vars.production` variants. Add a targeted `.dev.vars*` rule with `.dev.vars.example` exception before introducing secret variants. No leaked variant was found. |
| S03 | CODE CHANGE REQUIRED | `website/wrangler.toml [vars]` includes a replace-with AUTH_OTP_PEPPER placeholder. This is not a leaked live pepper, but a real value must never replace it in tracked vars. Remove it from public vars and use a Pages encrypted secret. Avoid same-name public-variable/secret collisions when selecting dashboard versus Wrangler as configuration source of truth. |
| S04 | CONFIGURATION REQUIRED | Provision separate high-entropy operator read/status/metadata/publication/revocation tokens and server peppers. Store website copies in encrypted bindings, operator copies in restricted local configuration, and keep staging separate. No token belongs in frontend build fields or researcher packages. A deploy-time Cloudflare API token is separate from Function/operator bindings and must never be a licence signing key. |
| S05 | READY | A targeted scan of 847 tracked text files up to 2 MB, including JSON text, found no live provider-token/private-key payload by its scanned signatures. Hits were private-key marker constants in `scripts/windows_packaging.py:35-37` and a TEST ONLY canary in `tests/runtime/test_customer_payload_inventory.py:147`. Tracked sensitive-path/extension checks found no real .pem/.key/.pfx/.p12/.dpapi/.sqlite/.db credential/database payloads. Tests use synthetic credentials; public keys/site keys are not private signing keys. This limited scan is not a universal secret-scan certificate. |
| S06 | CONFIGURATION REQUIRED | Review GitHub secret-scanning alerts, historical branches/tags, Actions logs/artifacts, collaborator access and release environment protections. This audit did not authenticate to GitHub/Cloudflare/Google, fetch missing history or inspect remote secret stores. It cannot certify that a secret never existed in deleted remote data. Rotate/revoke any actual exposure found by that review. |
| S07 | READY | `scripts/qs-local.ps1` deliberately enables loopback HTTP and TEST licensing/trust in isolated QA roots. Keep it a development aid, not a production launch configuration. It avoids printing credentials and clears operator credentials before desktop launch. |

Cloudflare documents encrypted runtime secret bindings and warns against sensitive
values in Wrangler vars. `.dev.vars` is local development input, not a production
secret deployment mechanism: [Pages bindings/secrets](https://developers.cloudflare.com/pages/functions/bindings/).

## Installation, release and operations findings

| ID | Classification | Evidence and required action |
| --- | --- | --- |
| D01 | READY | `backend/release.py` has desktop version 0.2.0 and default beta channel. website/package.json's 0.1.0 is frontend package metadata, not evidence the desktop is v0.1. Windows package/installer controls check clean source, inventory, excluded operator/private material, symlinks and suspicious content. Retain them. |
| D02 | CONFIGURATION REQUIRED | Build on the declared Windows x86_64 MSVC/Nuitka/PySide6 toolchain with Inno Setup 6, then audit actual installer/inventory. `build_windows_installer.py` currently supports GUI_ONLY assembly; do not promise a turnkey bundled scientific runtime/engine installation from that builder. No installer was built or inspected here. Include production public trust/origin for ordinary shortcut startup, not environment hacks. |
| D03 | CONFIGURATION REQUIRED | Decide supported platforms. Production device identity is Windows DPAPI only (`backend/licensing/device_identity.py::production_secure_store`); Linux fails closed. A Windows-only first cohort needs no new secure-store feature. An AppImage build does not prove production Linux licensing works. |
| D04 | OPTIONAL | `.github/workflows/release.yml` builds Windows AND Linux, and scripts/build_release.py requires both artifacts. Windows-only automated release selection would need changes there; an approved manual Windows artifact distribution avoids that dependency. validate.yml push coverage names the old beta-hardening branch (PR runs remain); adding this branch and website checks is advisable if CI is the release gate. |
| D05 | OPTIONAL | Decide installer Authenticode and approved signed/checksummed download distribution. Licence, update-manifest and installer keys are distinct. backend/update/config.py needs endpoint/public keys; absent update configuration safely disables updates, not licensing. Automatic updates are not a prerequisite for a small manually distributed closed beta. |
| D06 | CONFIGURATION REQUIRED | Before onboarding, run an authorized production-mode staging/pilot with real HTTPS, persistent non-TEST authority, independent client release trust, real OAuth/Turnstile/email and an installed shortcut launch. Repeat A/B authorization, denial, revocation/restart, replacement/same expiry, outage/restore and no-new-work gating; keep running jobs alive. M10 local acceptance is not this production proof. |

## Environment and secret inventory

These are names/purposes, never values. Do not copy a Functions environment wholesale
into frontend customFields or customer builds.

| Scope / classification | Names | Production treatment |
| --- | --- | --- |
| Pages build ? CONFIGURATION REQUIRED | TURNSTILE_SITE_KEY; BETA_TURNSTILE_TEST_MODE | Public widget key and false test flag; rebuild when changed. |
| Pages build ? CODE CHANGE REQUIRED | CLOUDFLARE_LOCAL; current hard-coded url/baseUrl | Do not enable the local build in production. Implement/select the approved HTTPS root profile (W02). |
| Functions config ? CONFIGURATION REQUIRED | BETA_ENVIRONMENT; BETA_ALLOWED_ORIGIN; BETA_PRIVACY_VERSION; BETA_TERMS_VERSION; AUTH_EMAIL_TEST_MODE; BETA_TURNSTILE_TEST_MODE | Exact production environment, canonical HTTPS origin, approved consent versions, both test flags false. Build/runtime flags must agree. |
| Functions resource ? CONFIGURATION REQUIRED | BETA_DB | Real production D1 binding, isolated from staging/preview. |
| Functions secrets ? CONFIGURATION REQUIRED | BETA_IDENTITY_PEPPER; AUTH_OTP_PEPPER; TURNSTILE_SECRET_KEY; GOOGLE_CLIENT_SECRET | High-entropy/real provider values in encrypted runtime secrets, not source/public vars. |
| Google config ? CONFIGURATION REQUIRED | GOOGLE_CLIENT_ID; GOOGLE_REDIRECT_URI | Public client ID and exact HTTPS callback. Client ID is not a secret. |
| Operator privileges ? CONFIGURATION REQUIRED | OPERATOR_SYNC_TOKEN; OPERATOR_STATUS_SYNC_TOKEN; OPERATOR_LICENCE_SYNC_TOKEN; OPERATOR_LICENCE_PUBLISH_TOKEN; OPERATOR_ACTIVATION_REVOKE_TOKEN | Five separate privileges, independently provisioned/rotatable. Read export includes applicant PII. Publication credentials are not signing keys. |
| Operator process ? CONFIGURATION REQUIRED | QS_OPERATOR_WEBSITE_URL; QS_OPERATOR_SYNC_TOKEN; QS_OPERATOR_STATUS_SYNC_TOKEN; QS_OPERATOR_LICENCE_SYNC_TOKEN; QS_OPERATOR_LICENCE_PUBLISH_TOKEN; QS_OPERATOR_ACTIVATION_REVOKE_TOKEN; BETA_ENVIRONMENT | Approved HTTPS origin and matching dedicated secrets. Production adapter changes are still required; setting these does not remove TEST guards. |
| Signer custody ? SECURITY BLOCKER | Protected signing-key file, public metadata, operator DB and restricted Windows account | Existing filenames/purposes are in signing.py/main_window.py. Provision only in a later approved ceremony. No generic licence private-key environment variable, website copy or customer build copy is needed. |
| Desktop public config ? CODE CHANGE REQUIRED | QS_WEBSITE_URL today; production issuer public trust set absent today | Release-controlled defaults/trust for ordinary installed launch, never keys supplied by the website response. |
| Desktop TEST controls ? SECURITY BLOCKER | QS_TEST_LICENSING; QS_TEST_LICENCE_TRUST_FILE; QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP | Not the production activation path or an enabled shipping TEST profile. Preserve separately scoped QA behavior. |
| QA helpers ? READY | QS_LOCAL_TEST_ROOT; QS_LOCAL_OPERATOR_ROOT; QS_LOCAL_TRUST_FILE; QS_LOCAL_DESKTOP_A_ROOT; QS_LOCAL_DESKTOP_B_ROOT; QS_LOCAL_WEBSITE_STATE_ROOT; QS_LOCAL_WEBSITE_URL | Local TEST only; not production secrets or a data-migration mechanism. |
| Build identity ? CONFIGURATION REQUIRED | QUANTUM_STUDIO_BUILD_CHANNEL; QUANTUM_STUDIO_BUILD_COMMIT; QUANTUM_STUDIO_BUILD_TIMESTAMP | Non-secret provenance from a clean approved source revision. |
| Optional updater ? OPTIONAL | QUANTUM_STUDIO_UPDATE_ENDPOINT; QUANTUM_STUDIO_UPDATE_PUBLIC_KEYS; QUANTUM_STUDIO_UPDATE_SIGNING_KEY; QUANTUM_STUDIO_UPDATE_SIGNING_KID | Endpoint/public keys are client settings. Updater private key belongs only to its separately protected release workflow. Existing workflow references GitHub secrets, not literal values. Never reuse the licence key. |
| Machine runtime ? READY | QUANTUM_STUDIO_DATA_ROOT; QUANTUM_STUDIO_LOCAL_TOOLS; QUANTUM_STUDIO_PSEUDO_CACHE | Per-machine/scientific settings, not entitlement authority. Do not ship a QA data directory with cached licences/private device keys. |
| Smoke/RC settings ? OPTIONAL | QUANTUM_STUDIO_PACKAGED_SMOKE; QUANTUM_STUDIO_PACKAGED_CATALOGUE_SMOKE; QUANTUM_STUDIO_PACKAGED_SCF_SMOKE; QUANTUM_STUDIO_PACKAGED_SMOKE_DATA; QUANTUM_STUDIO_RC_ENGINE_ROOT; QUANTUM_STUDIO_RC_SI_PSEUDO | Validation only, disabled in normal researcher launches. No licensing grant. |
| Deploy tools ? CONFIGURATION REQUIRED | Cloudflare account/project/database identifiers and any deploy API token; GitHub repository/release-environment credentials | External configuration, not frontend fields. Actual remote permissions/values were not inspected. |

Local `.dev.vars` contains configured names for the listed auth/operator variables and
Google settings; values were masked. Its Turnstile secret is a local placeholder.
This establishes neither provider validity nor production bindings. The tracked
example intentionally contains local/test values and placeholders; never upload it
as the production environment.

## Explicit localhost and TEST assumptions

| Classification | Exact source | Meaning |
| --- | --- | --- |
| CODE CHANGE REQUIRED | website/docusaurus.config.ts | Only local-root versus GitHub-Pages-subpath profiles exist. |
| CODE CHANGE REQUIRED | operator_tools/licence_manager/beta_worker.py | Explicit test mode, local/test environment, loopback URL and ephemeral authority required. |
| CODE CHANGE REQUIRED | operator_tools/licence_manager/issuance.py; licence_delivery.py; website_sync.py | Website signing/recovery/metadata/publication are TEST adapters. |
| CODE CHANGE REQUIRED | website/functions/_lib/licence-delivery.js; api/operator/activations/[activationId]/licence.js | TEST gates/issuer format prevent production delivery. |
| SECURITY BLOCKER | backend/licensing/local_test_trust.py; service.py | TEST trust works, but production trust and a shipping-profile boundary are missing. |
| CONFIGURATION REQUIRED | website/.dev.vars.example; scripts/qs-local.ps1 | Local callback/origin/roots and TEST flags are development defaults, not a production runbook. |
| READY | backend/licensing/connectors/{desktop_auth,licence_delivery,device_status}.py; website/functions/_lib/{desktop-auth,device-status}.js | HTTPS/proof paths can be retained. QA loopback branches are not a reason to migrate hosting. |

## Required code-change register ? future work only

Do not implement production by globally deleting TEST checks. Keep the known-good
LOCAL TEST workflow and explicit production adapters distinguishable.

| Change | Exact existing edit boundaries | Required result |
| --- | --- | --- |
| C01: website origin/root | website/docusaurus.config.ts | Approved HTTPS root routes/assets/OAuth/API paths; local profile unchanged. |
| C02: persistent website-activation issuance | operator_tools/licence_manager/signing.py; operator_tools/licence_manager/issuance.py; operator_tools/licence_manager/beta_worker.py; operator_tools/licence_manager/licence_delivery.py; operator_tools/licence_manager/website_sync.py | Protected persistent authority consumes original fixed grants; restart supports new replacement signing and old-envelope recovery. No term reset/new approval rule/arbitrary signing surface. Existing entitlements.py is reusable. |
| C03: production metadata/publication/delivery | website/functions/api/operator/activations/[activationId]/licence.js; website/functions/_lib/licence-delivery.js | Explicit HTTPS production gates/issuer identity with unchanged auth/binding/retry/immutable/REVOKED checks; no signing key on the website. |
| C04: production desktop trust/origin/profile | backend/licensing/service.py; backend/licensing/local_test_trust.py; backend/licensing/online_authorization.py; frontend/app/account_dialog.py; scripts/windows_packaging.py if public configuration is bundled as data | Ordinary installed launch uses approved production trust/origin, with no TEST requirement or response-provided trust. Reuse current connector/proof logic and preserve separate local QA. |
| C05: email adapter | website/functions/_lib/email-delivery.js | Real provider transport, controlled failures and no production devOtp/logging. Provider-specific future secret names are not yet implemented bindings. |
| C06: OTP/mode hardening | website/functions/_lib/auth.js; website/functions/_lib/email-delivery.js; website/functions/_lib/beta-registration.js; website/functions/_lib/google-auth.js | CSPRNG OTP, atomic limited attempts/single-use, fail-closed deployment modes/config; explicit local tests retained. |
| C07: Google browser-bound state | website/functions/_lib/google-auth.js; website/functions/api/auth/google/start.js; website/functions/api/auth/google/callback.js; website/functions/api/auth/google/pending.js; website/functions/api/auth/google/complete.js | Browser/session binding and atomic consumption for login and signup; PKCE/return-path protections retained. A focused migration is conditional on chosen storage design; none is mandated now. |
| C08: configuration/secret hygiene | website/wrangler.toml; website/.gitignore (root .gitignore only if sharing the rule) | Real non-secret DB/origin config, secret pepper removed from vars, secret-file variants ignored with example retained. No actual secrets committed. |
| C09: approved public copy | website/src/components/ProfessorPages.tsx; website/wrangler.toml consent versions/configuration | Approved privacy/terms/contact and accurate manual-approval versus automatic-issuance wording. No licence-policy change. |

Conditional/optional changes: Linux production key storage would require
`backend/licensing/device_identity.py` and an approved OS store; not necessary for a
Windows-only cohort. Windows-only use of existing release automation would require
`.github/workflows/release.yml` and `scripts/build_release.py` platform selection.
CI coverage improvements involve `.github/workflows/validate.yml`. Updater provisioning
involves `backend/update/config.py`, `scripts/build_release.py` and release secrets.
No new deployment automation is required for a manually controlled small beta.

Later regression changes should extend the existing Google/auth, metadata/delivery,
worker, desktop-status/trust and packaging suites, including
`website/tests/{google-auth.test.ts,auth-core.test.ts,auth-ux.test.ts,operator-licence-metadata.test.mjs,licence-delivery.test.mjs,licensing-acceptance.test.mjs}`,
`tests/licensing/{test_private_licence_manager.py,test_beta_worker.py,test_licence_delivery.py,test_device_status.py,test_website_sync.py}`
and runtime installer tests. Production coverage is additive; preserve M10 invariants.

## Files inspected / evidence inventory

Inspection combined targeted source reads, guard/callsite searches, environment-name
inventory and Git tracking checks; it was not a line-by-line formal review of every
tracked file. Braces below mean the listed existing files.

- Website configuration: `website/docusaurus.config.ts`, `website/package.json`, `website/wrangler.toml`, `.gitignore`, `website/.gitignore`, `website/.dev.vars.example`; local `.dev.vars` names/presence with values masked.
- Website runtime: `website/functions/_middleware.js`, `_lib/{auth,google-auth,email-delivery,beta-registration,beta-activation,operator-auth,desktop-auth,licence-delivery,device-status}.js`.
- Authentication routes: `website/functions/api/auth/{signup,login,resend-otp,verify-otp}.js` and `api/auth/google/{start,callback,pending,complete}.js`; application/activation and operator read/status/licence/revoke guards; tiny API wrappers inventoried with environment/callsite searches.
- Website frontend: `website/src/components/AuthPages.tsx`, `ProfessorPages.tsx`, `website/src/pages/desktop-auth.tsx`; tracked static-file inventory. No production public-key bundle or global headers configuration was found in that static inventory.
- D1: inventory of all 12 `website/migrations/*.sql`; focused grant/history/revocation/status reads in 0009-0012 plus auth/session/state SQL references. No database was opened or migrated. Prior acceptance/upgrade evidence came from documentation/tests, not a fresh run.
- Operator: `operator_tools/licence_manager/{beta_worker,signing,issuance,entitlements,licence_delivery,website_sync,device_revocation,main_window,app,paths}.py`, `scripts/run_licence_manager.py`, `scripts/qs-local.ps1`; entry points, guards and source environment inventory included.
- Desktop: `backend/licensing/{service,local_test_trust,online_authorization,verifier,device_identity,lease_store,licence_delivery,policy}.py`, `connectors/{desktop_auth,licence_delivery,device_status}.py`, `frontend/app/account_dialog.py`, `frontend/main.py` and established protected-work integration references.
- Distribution: `backend/release.py`, `backend/runtime/identity.py`, `backend/update/config.py`, `scripts/{build_windows,windows_packaging,package_exclusions,build_windows_installer,build_linux_appimage,build_release}.py`, `.github/workflows/{validate,release,linux-staging}.yml` inventory (release/validate read in detail).
- Validation context: `docs/beta/LICENSING_ACCEPTANCE.md`, `tests/licensing/test_account_entitlements.py`, status/delivery/worker test inventory, and `tests/runtime/test_customer_payload_inventory.py` secret-marker canary.

**READY ? preserve the baseline contract:** manual approval; exactly one beta grant
with 90-day fixed lifetime and default device_limit=1; normal authenticated device
activation; terminal per-activation revocation and slot release; explicit retry for
replacement authorization; original entitlement expiry; immutable signed envelopes;
Ed25519 device identity; current online authorization and durable revocation; read
access where permitted; no cancellation of already-running jobs on temporary outage.
The signed profile's existing internal `plan_id=pro` mapping and `offline_until` field
are not new commercial plans or an offline-grace grant. Preserve the format and the
mandatory online service gate. No host migration or grant-policy redesign follows
from this audit.

## Minimal ordered production plan ? future work, not authorization to execute

1. **P1A ? CONFIGURATION REQUIRED: fix scope and deployment identity.** Confirm Windows x86_64 first-cohort support, approved HTTPS domain, Pages project/production branch, staging separation, responsible operators, approved consent/contact copy and release gate. Retain Pages/Functions/D1 and M1-M10 invariants.
2. **P1B ? CODE CHANGE REQUIRED: implement missing production adapters and close security gaps.** Address C01-C09 using non-production test material first. Reuse the protected signer, original grant builder, immutable publication/proofs and central online gate. Do not globally disable TEST checks, change signed licence semantics, or reset dates.
3. **P1C ? CONFIGURATION REQUIRED: stage production-mode infrastructure.** Create isolated staging Pages/D1, apply existing migrations, set encrypted staging secrets, real-hostname OAuth/Turnstile/email and approved build settings. Test HTTPS flows with a separately controlled staging authority. Never make a public site work by setting BETA_ENVIRONMENT=local or enabling test flags.
4. **P1D ? SECURITY BLOCKER: separately approve and perform production signing-key custody/provisioning.** After code review, explicitly provision the protected persistent authority on its operator host; verify restart, backup/recovery and audit. Distribute only approved PUBLIC metadata to desktop trust. Licence/update/installer keys remain separate, and the licence private key never reaches the website. No key is generated by this audit.
5. **P1E ? CONFIGURATION REQUIRED: provision production resources and build the release.** Bind the real production D1 and apply the staged migration procedure. Configure production secrets, exact Google callback/widget hostnames, email sender, origin and consent versions. Build/audit the Windows installer from a clean approved revision with production public trust/origin; verify operator/TEST/private material is absent. Manual controlled Windows distribution is sufficient; no new deployment automation is necessary.
6. **P1F ? CONFIGURATION REQUIRED: pass the production-mode acceptance gate.** Later run regression suites, normal installed-shortcut startup and an authorized two-device real HTTPS pilot: human approval -> A Active -> B denied -> A revoked/restart -> B retry/replacement/original expiry -> outage denial -> restored Active. Check authentication consumption, immutable history, no TEST bypass, independent trust, backups and running-job continuity. Require human sign-off before inviting the cohort.
7. **P1G ? CONFIGURATION REQUIRED: open the approved small cohort and operate it.** Restrict operator access; monitor availability/errors/quotas; retain backups/audits; use the restartable persistent production authority. Do not add billing, renewal, organizations, self-service, new plans, remote wipe, offline grace or periodic authorization polling to this deployment work.

## Validation record and limits

**READY ? audit-only validation:** source/configuration reads, Git status/branch,
tracking/available-history queries, masked local configuration inventory, a targeted
read-only tracked-file scan, vendor documentation checks, and `git diff --check`
after creating this report. The new untracked report is also checked explicitly for
whitespace errors. Only this report may appear in the final working-tree status.
No tests, builds, migrations, deployments, production key generation, commits or pushes
were performed. Live Cloudflare/Google/GitHub configuration, actual release artifacts
and production acceptance remain unverified. Prior M10 acceptance is preserved,
not rerun or relabelled as production certification.
