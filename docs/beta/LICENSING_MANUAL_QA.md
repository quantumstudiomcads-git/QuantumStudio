# Final LOCAL TEST licensing run ? M10

Record PASS/FAIL and observed IDs/times for every checkbox. Do not record private keys,
operator credentials, OTPs, or applicant PII in the QA report. Automated acceptance is
separate from this manual run. No production deployment or signing is involved.

## 1. Prepare one new session

Start in repository root in PowerShell. Prerequisites: Python, Node, the existing
Windows-compatible dependencies, and a browser. For a fresh checkout only:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
Push-Location website
npm.cmd ci
Pop-Location
```

Choose a NEW unused absolute session root. Use this identical block in each terminal
(replace only the final run number when intentionally starting an entirely new run):

```powershell
$env:QS_LOCAL_TEST_ROOT = Join-Path ([IO.Path]::GetTempPath()) 'QuantumStudio-M10-Final-Run-1'
. .\scripts\qs-local.ps1
Show-QSConfig
```

- [ ] Confirm distinct Device A/B directories and coherent operator/trust/website-state paths.
- [ ] Do not reuse an earlier root with an unknown TEST issuer. Do not delete old QA data.

If website/.dev.vars already exists, preserve it and its existing secrets. Verify
its local values against the settings below; do not copy the example over it. For
an absent file, this exact block creates local TEST settings and random credentials
without displaying credential values:

```powershell
$devVars = Join-Path (Get-Location) 'website/.dev.vars'
function New-LocalSecret {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}
if (-not (Test-Path -LiteralPath $devVars)) {
    $lines = @('BETA_ENVIRONMENT=local', 'BETA_ALLOWED_ORIGIN=http://127.0.0.1:8788',
        'BETA_PRIVACY_VERSION=draft-0.1', 'BETA_TERMS_VERSION=draft-0.1',
        'BETA_TURNSTILE_TEST_MODE=true', 'AUTH_EMAIL_TEST_MODE=true',
        'TURNSTILE_SECRET_KEY=local-test-only-placeholder')
    foreach ($name in @('BETA_IDENTITY_PEPPER','AUTH_OTP_PEPPER','OPERATOR_SYNC_TOKEN',
        'OPERATOR_STATUS_SYNC_TOKEN','OPERATOR_ACTIVATION_REVOKE_TOKEN',
        'OPERATOR_LICENCE_SYNC_TOKEN','OPERATOR_LICENCE_PUBLISH_TOKEN')) {
        $lines += "$name=$(New-LocalSecret)"
    }
    [IO.File]::WriteAllLines($devVars, $lines, (New-Object Text.UTF8Encoding $false))
}
```

- [ ] Existing or new file: local origin is http://127.0.0.1:8788, both local test flags are true, consent versions/peppers and all five dedicated operator tokens are nonempty. Never commit this file.
- [ ] If existing file still has blank/replace-with tokens, generate each with New-LocalSecret above and set that key locally; do not print them or rotate a running session's credentials.

Migrate the isolated database before launch, in the setup terminal:

```powershell
Push-Location website
npx.cmd wrangler d1 migrations apply quantum-studio-beta --local --persist-to $script:QSWebsiteStateRoot --config wrangler.toml
if ($LASTEXITCODE -ne 0) { throw 'Local TEST migrations failed' }
Pop-Location
```

- [ ] All migrations through latest succeed; this is the same persist-to directory the website helper will use.

## 2. Start components in separate terminals

In every terminal first run the session-root/dot-source block above from repository
root. Keep the worker terminal/process alive through both issuances.

Website terminal:
```powershell
Start-QSWebsite
```
Worker terminal:
```powershell
Start-QSWorker
```
Operator terminal:
```powershell
Start-QSLicenceManager
```
Device A terminal:
```powershell
Start-QSDesktopA
```

- [ ] Website builds and serves http://127.0.0.1:8788. Worker shows no activations initially (or only this chosen clean session's records).
- [ ] Licence Manager is explicitly TEST MODE. Desktop initially denies protected functionality until a verified signed licence and online authorization exist.

## 3. Fresh account and approval

- [ ] Open http://127.0.0.1:8788/signup. Use a fresh email/account for this run.
- [ ] In local CAPTCHA verification enter `test-pass`; complete signup using the local TEST OTP displayed by the form/website console. No external email delivery is expected.
- [ ] Sign in, open http://127.0.0.1:8788/beta-access, submit the beta application with consent and local `test-pass`. Verify APPLIED.
- [ ] In Licence Manager Applications, Sync website applications. Select the new application, Review, then Approve locally. Record its opaque application ID.
- [ ] While website is still APPLIED, Sync status to website. Verify successful APPLIED -> UNDER_REVIEW -> APPROVED reconciliation.
- [ ] Retry Sync status: already_current/success, no extra review transition. Exactly one beta entitlement exists with duration 90 days, device_limit=1, revision=1.

For read-only DB checks use the setup terminal (root/dot-source block already loaded):
```powershell
Push-Location website
npx.cmd wrangler d1 execute quantum-studio-beta --local --persist-to $script:QSWebsiteStateRoot --config wrangler.toml --command "SELECT entitlement_id,application_id,plan_id,starts_at,expires_at,device_limit,revision FROM account_entitlements"
Pop-Location
```
- [ ] Record entitlement ID, starts_at, expires_at, limit and revision; use them unchanged in later comparisons.

## 4. Device A and one-device denial

- [ ] On A, Account / Licensing -> Sign in / Activate; browser signs into the SAME account and confirms this device. Verify AUTHORIZED.
- [ ] Keep the worker running; wait for one signed licence/publication. On A, Check licence if automatic retrieval initially said pending. Verify Active, original expiry, TEST trust indicator, and successful new protected-work authorization.
- [ ] Retry Check licence/worker polls. Licence ID and signed bytes remain unchanged; no duplicate issuance.
- [ ] In a new Device B terminal load the SAME session configuration and run `Start-QSDesktopB`.
- [ ] On B, Sign in / Activate and confirm using the SAME account. Verify FLAGGED/DEVICE_LIMIT, no Active access and no licence issued for B. Entitlement fields are unchanged.

## 5. Revoke A, replace with B

- [ ] In Licence Manager Activation Requests, Refresh website activations. Select A's exact activation ID, Revoke device, choose DEVICE_REPLACED, confirm.
- [ ] Refresh: A is REVOKED. B stays FLAGGED until B explicitly retries normal Sign in / Activate.
- [ ] On A, Check licence: Revoked, protected work denied. Close A and relaunch `Start-QSDesktopA`: still Revoked after restart; original identity/cache/trust retained.
- [ ] On B, repeat Sign in / Activate and browser confirmation. Verify AUTHORIZED. Keep the ORIGINAL worker process alive; do not issue manually from a different Licence Manager signer.
- [ ] Worker skips A and issues/publishes one B licence. B Check licence -> Active.
- [ ] B expiry equals the originally recorded entitlement expiry, not now +90 days. All entitlement fields remain unchanged. Historical A activation/licence/publication remain stored.
- [ ] Repeated revocation with the identical reason is already_revoked and preserves the first timestamp/reason; no second audit. The UI deliberately disables revocation for REVOKED selections; this retry is also covered by automated endpoint/client acceptance.

Read-only history/audit checks in setup terminal:
```powershell
Push-Location website
npx.cmd wrangler d1 execute quantum-studio-beta --local --persist-to $script:QSWebsiteStateRoot --config wrangler.toml --command "SELECT activation_request_id,installation_id,status,revoked_at,revocation_reason_code,authorization_revision,licence_id FROM beta_activations; SELECT event_type,old_status,new_status,event_timestamp,metadata_json FROM beta_audit_events WHERE event_type='OPERATOR_DEVICE_REVOKED'; SELECT activation_request_id,licence_id,envelope_sha256 FROM published_licences; SELECT entitlement_id,starts_at,expires_at,device_limit,revision FROM account_entitlements"
Pop-Location
```
- [ ] Exactly one A revocation audit, unchanged grant, two historical device licence references/publications; no extra signed B licence after retries.

## 6. Real outage, restart and recovery

- [ ] Stop ONLY the website terminal with Ctrl+C. Keep the signer worker alive (it may report safe fetch failures).
- [ ] Close and relaunch B with `Start-QSDesktopB`: Online validation required. Cached envelope alone must not show Active. New protected compute/Device Builder access denied. Existing project/result read access remains available.
- [ ] Relaunch A with `Start-QSDesktopA` while offline: Revoked remains visible and protected work denied.
- [ ] In the original website terminal restart with `Start-QSWebsite -SkipBuild`; same state root and credentials.
- [ ] On B, Check licence: fresh validation returns Active. On A, Check licence: still Revoked. No envelope rewrite, new entitlement, expiry extension, or trust rotation.
- [ ] If an already-running configured scientific job is available, stop the website after it starts: it must not be killed. Starting another protected job must deny until fresh validation succeeds. Do not fabricate a scientific job merely to check a UI label; record not exercised if no executable setup exists.

## 7. Finish and record limitations

- [ ] Save PASS/FAIL, opaque IDs, original expiry, observed statuses, and any safe error text. Record separately which native GUI/running-job checks were actually exercised.
- [ ] Preserve session roots and issuer.json for investigation. Stop processes when finished. No source commit/push is part of this checklist.
- [ ] A stopped TEST worker cannot recreate its ephemeral signing key. Existing envelopes can be recovered; new signatures after restart need a fresh isolated operator/trust session. Never delete/overwrite old trust to bypass this conflict.
- [ ] Production signing/email/deployment, billing/renewals/self-service, offline grace, remote wipe, organizations, new plans and periodic authorization polling are not acceptance claims.
