# B4 Final Acceptance

## Result and provenance

Automated B4 gates pass for the accepted r28 candidate. The only unresolved
gate is one normal-user Windows DPAPI run; therefore the current result is
**B4 HUMAN CONFIRMATION REQUIRED**.

r28 is `E:\QuantumStudio-W8\build\QuantumStudio-0.2.0-development-real-r28\main.dist`,
built from clean source commit `42bd7e1ebc7e01e3149b830da67de0fc1638214d` on
`beta-hardening-v0.2`. The package measures 371 files and 502,217,385 bytes;
`QuantumStudio.exe` is 300,140,544 bytes with SHA-256
`1122712B403A6BC885EAC4CA402BEBB384F4A2F6F6D75D1A28CF8092516E1749`.
Documentation-only changes after that commit do not require r29.

## Automated validation

- Package audit: PASS. Qt `qwindows.dll`, application assets, manifests, and
  `cryptography/hazmat/bindings/_rust.pyd` are present; no engine/scientific
  payloads, checkout metadata, or oversized files are present.
- Focused selectors: `tests/licensing/test_b4_licensing.py` and
  `tests/runtime/test_w6_windows_packaging.py`: 25 passed, 1 cache warning.
- Full native suite: 534 passed, 0 failed, 0 skipped, 0 xfail, 320 dependency
  warnings, 11 subtests, 34.36 seconds.
- `compileall` for backend, frontend, launcher, scripts, and runtime_agent:
  PASS. `git diff --check`: PASS.
- Normal startup remained alive for 12 seconds from the original bundle and
  complete copies at a clean directory, a path containing spaces, and a
  Unicode path. Visible click-through and ACL interaction were unavailable in
  this execution context and are not represented as passed.

## Licensing boundary

The architecture is: device identity → signed lease verification → desktop
entitlement policy → implementation-state and catalogue authorization. Prices
remain display/commercial policy, not authorization logic. Production uses
Windows DPAPI for the device private key and has no plaintext fallback.

With no valid entitlement, the GUI and read-only project/result paths remain
available where policy permits; paid create/execute operations and Device
Builder are denied. There is no server, fabricated lease, implicit Pro,
Organization fallback, or environment unlock in production composition.

| Plan | SCF | NSCF | Phonons | Device Builder |
|---|---|---|---|---|
| Free Starter | Policy/core only | Policy/core only | Policy/core only | Denied |
| Student | Allowed | Allowed | Allowed | Denied |
| Plus | Paid entitlement | Paid entitlement | Paid entitlement | Denied |
| Plus Trial | Paid entitlement | Paid entitlement | Paid entitlement | Denied |
| Pro | Allowed if implemented | Allowed if implemented | Allowed if implemented | Allowed |
| Organization | Allowed if implemented | Allowed if implemented | Allowed if implemented | Allowed |

The source-controlled Student primitive set is exactly `calc:scf`,
`calc:nscf`, and `calc:phonons`. Planned catalogue entries stay
non-executable even under Pro because implementation state wins entitlement.

Expired leases deny paid execution while preserving project/result reads and
avoiding deletion, encryption, or mutation. The mock authority prevents trial
replay after local cache removal. Pro allows device A, rejects simultaneous
device B with `SESSION_LIMIT_REACHED`, then allows B after A closes.
Organization retains named seats, five-seat commercial metadata, independent
seat/session identity, and Device Builder entitlement.

## Security and privacy

Secret and backdoor audits found no production/test private signing key,
master unlock, auth/billing secret, or environment/developer unlock. Trusted
public verification keys are permitted. The source security audit found no
`shell=True`, `os.system`, unsafe pickle/YAML loading, or arbitrary archive
extraction; Qt `app.exec()`/dialog `exec()` calls and guarded cleanup are not
unsafe execution mechanisms.

Diagnostics may expose plan ID, entitlement state, expiry, device-registration
status, safe error codes, and refresh status. They do not expose a raw lease,
private key, auth/refresh token, billing data, verification documents, or
signing material. No recent packaged log was available under the canonical
local log directory in this run; the source redaction contract passed.

## DPAPI diagnostic

The validation-only source is outside the repository at
`E:\QuantumStudio-W8\validation\b4-dpapi-interactive\B4_DPAPI_Diagnostic.py`.
The packaged executable is:

`E:\QuantumStudio-W8\validation\b4-dpapi-interactive\package\B4_DPAPI_Diagnostic.dist\B4_DPAPI_Diagnostic.exe`

It uses the production `WindowsDPAPIKeyStore` and `DeviceIdentityService`,
prints only safe status lines, compares public identity hashes, and checks
that the protected blob does not contain the plaintext private key. The Codex
execution context returned `HUMAN INTERACTIVE VALIDATION REQUIRED`; no fake
pass is claimed.

## Deferred work

Production signing-key/KMS, HTTPS licensing service, OIDC Authorization Code +
PKCE, billing, student verification, organization administration and seat
backend, session-concurrency backend, production trial authority, payment
credit logic, Authenticode, and installer integration remain deferred.

Scientific compatibility is explicitly unchanged: QE, EPW, Wannier90,
BoltzTraP2, transport, optical, vibrational, pseudopotential science,
ResultStore interpretation, `.qs` schema, Builder renderer, and catalogue 148.
