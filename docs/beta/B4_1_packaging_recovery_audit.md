# B4.1 Packaging Recovery Audit

This record supersedes stale B4 evidence for earlier package attempts. r28 was
built from clean committed source at `42bd7e1`; acceptance documentation was
added afterward and does not invalidate the package.

- Branch at build: `beta-hardening-v0.2`
- r28 source commit: `42bd7e1ebc7e01e3149b830da67de0fc1638214d`
- Candidate: `E:\QuantumStudio-W8\build\QuantumStudio-0.2.0-development-real-r28\main.dist`
- Build: Nuitka 4.1.1 standalone, Windows x86_64, Python 3.13.15, PySide6 6.11.2
- Measured package: 371 files, 502,217,385 bytes
- Measured executable: 300,140,544 bytes

## Automated evidence

- r28 provenance: PASS; no production source changes were made for acceptance
- Required standalone assets and cryptography Rust extension: PASS
- Forbidden scientific executables, checkout metadata, and oversized files: none
- Focused licensing/packaging tests: 25 passed, 1 pytest cache warning
- Full native suite: 534 passed, 0 failed, 0 skipped, 0 xfail, 320 dependency warnings, 11 subtests, 34.36 seconds
- Normal startup probes: original, clean-copy, spaces-path, and Unicode-path PASS; each remained alive for 12 seconds
- The previously observed SciPy MemoryError did not reproduce in the successful clean r28 build; no SciPy fix is claimed.

## Historical gates before final closure

- B4.2 binding diagnosis is blocked pending the v3 raw ctypes oracle result from the user's normal account; the independent PowerShell/.NET evidence proves the previous generic profile classification was insufficient.
- Visible GUI click-through and ACL/read-only interaction were not available in this execution context.
- W7 installer integration, Authenticode, and legal review remain later-phase work.

## Final B4 closure

The remaining normal-user licensing and device-identity gate passed through the
v7 isolated diagnostic, including CurrentUser DPAPI protection and
cross-process identity persistence. r28 is the accepted B4 package; it remains
bound to source commit `42bd7e1ebc7e01e3149b830da67de0fc1638214d`. Subsequent
commits are documentation-only acceptance records, so no rebuild was required
and r28 is not superseded.
