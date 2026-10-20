# Milestone 8: automatic LOCAL TEST issuance

Baseline: `149e7e7` on `beta-hardening-v0.2`, clean before implementation.
This is an explicit TEST QA automation extension. Production signing remains
unavailable. Website signing, endpoint validation, licence format, desktop
verification/policy, and the manual Licence Manager buttons are unchanged.

## Architecture and eligibility

`scripts/run_beta_licence_worker.py` launches the Qt-free
`operator_tools.licence_manager.beta_worker` service. One shot is the default;
`--poll-interval 2..60` explicitly repeats, with finite existing HTTP timeouts
and Ctrl+C to stop. No daemon or desktop infinite retry is installed.

All configuration is checked before opening storage or signing: `--test-mode`,
`BETA_ENVIRONMENT=local|test`, an explicit absolute `--test-data-root`, an explicit
absolute `--trust-file`, a loopback `QS_OPERATOR_WEBSITE_URL`, and the three
nonempty operator credentials. The default production operator root is refused.
The existing fail-closed CurrentUser DPAPI database bootstrap is reused. Tokens
remain process environment values and are excluded from dataclass repr, output,
audit details and database storage. No signer private key is persisted.

Each pass fetches the existing strict operator activation export. A malformed
export fails the entire fetch without issuing. The service also validates each
activation before reconciliation. Only AUTHORIZED records with valid UUIDs,
full lowercase SHA-256 public hash, matching `dev_` installation ID, supported
platform/architecture, valid application version, authorization timestamp,
no flag/revocation, and no duplicate device activation can proceed.

Reconciliation checks local/remote licence identity first. Remote licence
metadata without the local envelope is **recovery_required**, including partial
remote metadata. Restore the original matched operator database/data-key pair;
never create replacement storage to work around this state. Existing envelopes
are recovered and verified using M7 `stored_test_licence`, including the original
persisted TEST public key. A different website licence ID fails closed.

Before fresh issuance, active website-path local licences for the same device
and active legacy licences for that application block automation. M4 website
authorization remains responsible for its configured device cap; different
AUTHORIZED devices for the same applicant remain supported. No second local
applicant approval or separate entitlement policy is introduced.

New signing uses exactly M5 `issue_website_activation_for_testing`. Its existing
SQLite transaction/unique activation mapping remains authoritative. A per-root
OS lock serializes workers and is released on process exit; a stale lock file
alone does not block restart. Manual issuance remains idempotent through M5.

After recovery/issuance, the service verifies/creates explicit local trust,
then calls existing M5 metadata sync and M7 immutable publication. Trust is
prepared before network publication so a desktop check cannot race missing
trust. Metadata is synchronized idempotently on every retry before publication.
A failed sync or publish keeps the same local envelope. Identical publication
returns already_current; conflicting publication is never replaced.

Each activation produces a concise result. The existing tamper-evident local
audit records eligibility, recovered-original state, issuance, trust creation/
conflict, metadata, publication, failure and recovery-required decisions. IDs
and controlled stage/result codes are recorded, without PII, raw exceptions or
credentials. Known HTTP validation codes use existing redacted client messages.
Audit/storage failures stop the command rather than continue unaudited signing.
One-shot exits 0 for completed/unauthorized-only work, 1 for an activation/fetch
failure or recovery decision, and 2 for configuration/storage failure.

## Explicit TEST public trust and restart

The configured file contains exactly `schema_version`, `domain: test-licence`,
`algorithm: Ed25519`, `kid`, and `public_key`. It is derived from the verified
local envelope and persisted original public signing metadata, never a website
response. A complete flushed temporary file is published with an atomic
no-clobber hard link. Existing identical trust is accepted without rewriting;
malformed/different trust is preserved and reported as a conflict. Filesystems
without hard-link support fail closed. NTFS is the Windows QA target.

The desktop still requires both `QS_TEST_LICENSING=1` and explicit
`QS_TEST_LICENCE_TRUST_FILE`. Existing Check licence reloads only that local file
when a signed artifact arrives. Authorization/pending metadata never grants
access, and production `LicensingService.production()` remains unchanged.

A new TEST worker process has a new ephemeral signer. It can recover/sync/
republish old envelopes and their original trust without signing again. It
cannot sign *new* activations under an old trust file because the old private
key no longer exists. It refuses this before signing. It also refuses silent
rotation when prior issuer records exist but the trust file has disappeared.
Keep the polling worker alive while adding multiple new QA devices. For an
intentionally separate TEST issuer use separate storage/trust and isolated
QA desktop/device state; never discard the original storage for an existing
website activation. Multi-key trust, persistent TEST signing keys, renewal,
production provisioning and key rotation are deferred.

## Exact local manual QA commands

Use three PowerShell terminals from the canonical repository. Retain the
already verified M6/M7 local `.dev.vars` configuration; its read, metadata and
publication tokens must match the worker prompts below. Never paste tokens
into command history. No migration is added by M8; the baseline already has
local migrations through 0008.

Website terminal:

```powershell
Set-Location 'C:\Users\Admin\Desktop\AVI\CODING\PROJECTS\bhargava\QuantumStudio\website'
$env:CLOUDFLARE_LOCAL = 'true'
npm run build
npm run pages:dev
```

Worker terminal, from the repository root:

```powershell
$env:BETA_ENVIRONMENT = 'local'
$env:QS_OPERATOR_WEBSITE_URL = 'http://localhost:8788'
$env:QS_OPERATOR_SYNC_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Local read token' -AsSecureString)).Password
$env:QS_OPERATOR_LICENCE_SYNC_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Local metadata token' -AsSecureString)).Password
$env:QS_OPERATOR_LICENCE_PUBLISH_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Local publication token' -AsSecureString)).Password
.\.venv\Scripts\python.exe scripts/run_beta_licence_worker.py --test-mode --test-data-root 'C:\Temp\QuantumStudio-M8-Operator' --trust-file 'C:\Temp\QuantumStudio-M8-issuer.json' --poll-interval 5
```

For an existing M7 activation use its **original** persistent TEST operator root
and original trust path instead of the example fresh M8 paths. Missing envelope
with website metadata must report recovery_required; restore original storage.
A new M8 QA activation with no prior licence can use the example paths.
Omit `--poll-interval 5` for a single pass. Do not run operator GUI actions
concurrently while testing automation.

Desktop terminal, from the repository root:

```powershell
$env:QS_WEBSITE_URL = 'http://localhost:8788'
$env:QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP = '1'
$env:QS_TEST_LICENSING = '1'
$env:QS_TEST_LICENCE_TRUST_FILE = 'C:\Temp\QuantumStudio-M8-issuer.json'
.\.venv\Scripts\python.exe -m frontend.main
```

Use the normal same Windows account/runtime data root across restarts. Activate
an APPROVED beta user through Help -> Account / Licensing and browser
confirmation. Do not open Licence Manager. Until publication the desktop may
show Device authorized - licence pending. The worker should report complete
published. Click Check licence, verify Active and record device/licence IDs.
Stop worker and website with Ctrl+C, restart desktop with the same environment,
and verify Active offline with the same IDs. Restart website and the worker
with the same paths; expect complete already_current and one local licence.
Manual browser/GUI acceptance remains a human QA step; offscreen checks do not
prove browser login or interactive click-through.

## Validation and scope

Focused `tests/licensing/test_beta_worker.py` covers real M5 signing, real HTTP
clients, idempotency, all eligibility refusals, remote/local recovery, metadata/
publication failure retries, immutable conflicts, public-only trust, no-clobber
publication races, prior signer recovery, actual process restarts, actual Windows
DPAPI CLI storage/restart, multiple M4 devices, configuration refusal, audit
redaction, worker locking, Qt-free subprocess import and existing desktop
proof/retrieval/verification/cache reuse. Existing M5/M6/M7 suites remain intact.

Files added: worker service, CLI launcher, focused test module and this guide.
No existing source, public signature, database schema, website, frontend,
production trust or geometry/scientific code is modified. Validation counts
and offscreen/manual status are recorded in the implementation report.
