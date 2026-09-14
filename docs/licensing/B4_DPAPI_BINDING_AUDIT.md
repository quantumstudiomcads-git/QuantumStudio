# B4.2 Windows DPAPI Binding Audit

## Status

The user's normal Windows account independently reports successful
CurrentUser DPAPI through PowerShell and .NET. The previous profile-failure
classification is therefore superseded for that account.

The Codex execution token cannot validate the raw native oracle: both the
source and frozen v3 oracle fail at `CryptProtectData` with Windows error 2
(`ERROR_FILE_NOT_FOUND`). The same token also fails through PowerShell's
independent DPAPI path. No production defect is proven yet, so production
licensing code was not changed.

## Comparison

| Area | Known-good target | Production before | Difference | Security impact |
|---|---|---|---|---|
| DLL loading | `WinDLL("crypt32.dll", use_last_error=True)` | Same, capitalization only | None material | None |
| Calling convention | Windows `WinDLL` ABI | `WinDLL` ABI | None | None |
| `DATA_BLOB` | `DWORD` + native `BYTE*` | `DWORD` + native `c_byte*` | Signedness is ABI-neutral for a byte pointer | None identified |
| 64-bit layout | 16 bytes; pointer offset 8 | 16 bytes; pointer offset 8 | None | None |
| Input lifetime | Explicit ctypes-owned buffer retained across call | `create_string_buffer` retained locally | None identified | None |
| Protect argtypes | Canonical pointer/null types | Pointer plus `c_void_p` for nullable pointers | NULL representation is ABI-compatible | None identified |
| Unprotect description | `LPWSTR*` | Nullable `c_void_p` | Production discards description | No secret exposure; not a protect-stage cause |
| Entropy/reserved/prompt | NULL, NULL, NULL | NULL, NULL, NULL | None | None |
| Flags | `0`, CurrentUser | `0`, CurrentUser | None | User scope preserved |
| Error capture | `get_last_error()` immediately | Same | None | Safe numeric errors only |
| Output ownership | Copy bytes, then `LocalFree` | Copy bytes, then `LocalFree` | Production does not explicitly type `LocalFree` | Only relevant after successful protect |

## Layer results

| Layer | Result in Codex token |
|---|---|
| Raw ctypes | `RAW_CTYPES_DPAPI_FAILED:CryptProtectData:2` |
| Production low-level | `B4_DPAPI_FAILED:PRODUCTION_PROTECT:2` |
| Production SecureStore | Not reached; protection fails first |
| DeviceIdentity | Not reached; protection fails first |
| Frozen v3 diagnostic | `RAW_CTYPES_DPAPI_FAILED:CryptProtectData:2` |

The first failing layer available in this execution context is the native
call itself, but this does not distinguish a token-specific Windows condition
from a binding defect on the user's account. The v3 executable must be run in
that account before a production fix is justified.

## Security decision

No machine-scope flag, plaintext fallback, alternate key store, or licensing
policy change was introduced. r28 remains preserved as a historical package;
it is not accepted as B4 while the normal-user v3 oracle is unresolved.
