# W6 Native Windows Build Audit

## Implemented architecture

- `scripts/build_windows.py` creates a reproducible Windows-only Nuitka standalone build plan. On Linux it supports `--dry-run` only and explicitly refuses to claim a native build.
- `scripts/windows_packaging.py` owns structured Nuitka argv construction, build metadata, safe recognized-output cleanup, W7 installer-input metadata, and package-content auditing.
- `backend.runtime.resources.ApplicationResources` centralizes source-vs-frozen resource resolution. Mutable state uses the existing `RuntimePaths` contract, not the executable directory.
- `scripts/windows_integration_smoke.py` is read-only by default and emits JSON diagnostics. It does not provision WSL, mutate distros, install packs, or execute science.

## Startup contract

Startup initializes writable application data only. It neither requires nor provisions WSL, `QuantumStudioRuntime`, a runtime agent, an Engine Pack, network connectivity, or scientific engines. Project Hub/Builder/Calculate/Analyze remain independently constructible; managed runtime readiness is execution-specific.

## Package / installer boundary

The standalone bundle includes application modules, W1–W5 host runtime/control code, PySide6 support, canonical assets, and build metadata. It excludes test trees, checkout metadata, virtualenvs, rootfs/VHDX, and scientific executables. The Engine Pack remains a separate legal/distribution artifact. W7 will consume the generated installer-input manifest for GUI bundle, pending runtime image, runtime agent compatibility, Engine Pack descriptor, and notices slots.

## Explicit physical gates

**REAL_WINDOWS_BUILD: PENDING_REAL_WINDOWS.** No native executable, Windows launch, relocation, read-only install-root, or managed-runtime probe was claimed from Linux tests. Code signing is **PENDING**; W7 installer work is deferred; WSL prerequisite/UAC/reboot work is deferred; public Engine Pack review is **PENDING**; real QE parity is W8.
