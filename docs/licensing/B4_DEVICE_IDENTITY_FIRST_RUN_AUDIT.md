# B4 Device Identity First-Run Audit

## Purpose

This audit validates the complete first-run `DeviceIdentity` lifecycle under a
normal Windows user profile. The external diagnostic uses an isolated path
under `E:\QuantumStudio-W8\validation\b4-device-identity`; it does not require
or modify `%LOCALAPPDATA%\QuantumStudio\licensing`.

## First-run contract

The production call chain is:

`frontend.main` → `initialize_application_data()` → `LicensingService.production()` → `production_secure_store()` → `DeviceIdentityService.load_or_create()` → `WindowsDPAPIKeyStore`.

When `device-key.dpapi` is absent, `WindowsDPAPIKeyStore.load_private_key()`
returns `None`. `DeviceIdentityService.load_or_create()` then generates an
Ed25519 private key, serializes it only in memory, and calls
`save_private_key()`. That method creates the licensing parent directory,
protects the private key with Windows CurrentUser DPAPI, and persists it
atomically. Reload reconstructs the identity and derives the stable public-only
`public_key_hash`.

## Final normal-user validation

The user ran the v7 packaged diagnostic from a normal Windows PowerShell
session. Its exact successful output was:

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

This proves fresh-store handling, absent-key semantics, identity generation,
CurrentUser DPAPI protection, parent-directory creation, encrypted key
persistence, same-process reload, cross-process reload, stable public identity
hashing, absence of obvious plaintext private-key leakage, and isolated
first-run licensing-service composition.

## Security conclusions

- CurrentUser DPAPI is retained; `CRYPTPROTECT_LOCAL_MACHINE` is not used.
- There is no plaintext fallback, private-key logging, or private-key
  diagnostic output.
- The device key survives a new process for the same Windows user and machine.
- Paid capabilities remain entitlement-gated; successful service initialization
  does not grant a plan, a trial, Pro, or Organization access.

## Diagnostic history and superseding evidence

The earlier Codex-context CurrentUser DPAPI failures were specific to that
execution context and were not product defects. The normal user profile was
healthy: PowerShell DPAPI, .NET `ProtectedData` CurrentUser, raw ctypes DPAPI,
the production DPAPI wrapper, and `WindowsDPAPIKeyStore` all passed.

| Generation | Result | Classification |
| --- | --- | --- |
| v3 | Raw ctypes, production DPAPI, and SecureStore passed in the normal-user context; the diagnostic referenced nonexistent `public_key_bytes`. | Harness defect |
| v4 | Corrected to `public_key_hash`; remaining first-run isolation was not yet understood. | Harness investigation |
| v5 | First-run identity creation and same-process reload passed; subprocess launch raised `FileNotFoundError`. | Harness defect |
| v6 | Attempted self-relaunch through `sys.executable`; frozen executable resolution still failed. | Harness defect |
| v7 | Used `GetModuleFileNameW` to resolve and relaunch the running frozen executable. Cross-process validation passed. | Final PASS |

## Final result

**DEVICE IDENTITY PASS**
