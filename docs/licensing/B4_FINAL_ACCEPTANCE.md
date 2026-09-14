# B4 Final Acceptance

## Result and accepted package

**B4 PASS.** The accepted standalone package is r28:

`E:\QuantumStudio-W8\build\QuantumStudio-0.2.0-development-real-r28\main.dist`

It was built from clean source commit
`42bd7e1ebc7e01e3149b830da67de0fc1638214d`. Later commits record validation
and acceptance only; they do not alter r28 provenance or require a rebuild.

- `QuantumStudio.exe`: 300,140,544 bytes
- SHA-256: `1122712B403A6BC885EAC4CA402BEBB384F4A2F6F6D75D1A28CF8092516E1749`
- Bundle: 371 files, 502,217,385 bytes
- Toolchain: Python 3.13.15, PySide6/Qt 6.11.2, Nuitka 4.1.1,
  cryptography 46.0.5, MSVC v143/14.44.35207, Windows SDK 10.0.26100.0

## Acceptance matrix

| Area | Result |
| --- | --- |
| Ed25519 device identity | PASS |
| CurrentUser DPAPI storage | PASS |
| Raw ctypes DPAPI | PASS |
| Production DPAPI wrapper | PASS |
| SecureStore roundtrip | PASS |
| Fresh identity creation | PASS |
| Directory auto-creation | PASS |
| Encrypted key persistence | PASS |
| Same-process reload | PASS |
| Cross-process persistence | PASS |
| Stable `public_key_hash` | PASS |
| No plaintext private key | PASS |
| LicensingService first-run | PASS |
| Entitlement fail-closed behavior | PASS |
| Device Builder gating | PASS |
| Student primitive grants | PASS |
| Trial replay controls | PASS |
| Pro session/device policy | PASS |
| Organization policy metadata | PASS |
| Diagnostics privacy | PASS |
| Windows standalone packaging | PASS |
| Startup path matrix | PASS |
| Catalogue 148 | PASS |
| Scientific compatibility | PASS |

## Validation record

The authoritative normal-user v7 device-identity diagnostic completed with:

```text
FRESH_STORE_OK
ABSENT_DEVICE_KEY_OK
ABSENT_LOAD_RESULT:NONE
IDENTITY_CREATE_OK
LICENSING_DIRECTORY_CREATED_OK
DEVICE_KEY_FILE_CREATED_OK
IDENTITY_RELOAD_OK
DEVICE_IDENTITY_PERSISTENCE_OK
PRIVATE_KEY_NOT_PLAINTEXT_OK
LICENSING_SERVICE_FIRST_RUN_OK
B4_DEVICE_IDENTITY_OK
```

The full native regression applicable to r28 source was 534 passed, 0 failed,
0 skipped, 320 warnings, and 11 subtests. The focused selectors
`tests/licensing/test_b4_licensing.py` and
`tests/runtime/test_w6_windows_packaging.py` produced 25 passed. No production
code changed during final DPAPI/device-identity diagnostics, so these prior
source/package results remain applicable; this closure does not claim a new
regression run.

The package audit passed: Qt platform support, application assets, build/install
manifests, and `cryptography/hazmat/bindings/_rust.pyd` are present; scientific
engine payloads are excluded. Original, clean-copy, spaces-path, and Unicode
startup probes passed.

## Licensing and privacy guarantees

The client boundary is device identity → signed lease verification → entitlement
policy → implementation-state/catalogue authorization. Prices are commercial
policy, never authorization logic. With no valid entitlement, startup and
permitted read-only data paths remain available while paid create/execute
operations and Device Builder remain denied. There is no implicit Pro or
Organization grant, environment unlock, fabricated lease, or plaintext secure
storage fallback.

| Plan | Commercial policy | Device Builder |
| --- | --- | --- |
| Free Starter | $0; 7 days; 1 device | Denied |
| Student | $20/month; 1 device; `calc:scf`, `calc:nscf`, `calc:phonons` | Denied |
| Plus | $50/month; 1 device | Denied |
| Plus Trial | $20 for 7 days; server-side billing credit only | Denied |
| Pro | $80/month; 1 named user; 2 devices; 1 active session | Included |
| Organization | $200/month; 5 named seats; +$35/month per seat; 1 session per seat | Included |
| Enterprise | Future | Future |

Expired leases deny paid execution without deleting, encrypting, or mutating
user data. Planned calculations remain non-executable when their implementation
state is not implemented. Diagnostics and logs exclude raw leases, device
private keys, auth/refresh tokens, billing data, and signing material.

## Superseding DPAPI narrative

Earlier Codex-context failures were initially described too broadly as a
Windows profile/DPAPI problem. They were not product failures. The normal
Windows account proved a loaded healthy profile, PowerShell DPAPI, .NET
CurrentUser `ProtectedData`, raw ctypes DPAPI, the production wrapper,
SecureStore, fresh device identity creation, and cross-process persistence.
Intermediate failures were external diagnostic-harness defects, fixed in v7
with `GetModuleFileNameW` self-relaunch resolution.

## Deferred server and release integration

Production signing-key/KMS, an HTTPS licensing service, OIDC Authorization
Code + PKCE, billing, student verification, organization administration,
server-authoritative sessions, trial authority, payment-credit logic,
Authenticode, and installer licensing integration are deferred post-B4 work.

## Scientific compatibility

B4 did not modify QE, EPW, Wannier90, BoltzTraP2, transport, optical,
vibrational, or pseudopotential science; ResultStore semantics; the `.qs`
schema; the Builder renderer; or catalogue contents. The catalogue remains 148.
