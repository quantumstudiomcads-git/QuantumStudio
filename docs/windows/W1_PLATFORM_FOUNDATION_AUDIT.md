# W1 Platform Foundation Audit

## Implemented

- Qt-free `OperatingSystem` and `PlatformInfo` model with injectable identities for Linux/Windows/unknown tests.
- Windows `%APPDATA%` configuration and `%LOCALAPPDATA%` data/cache/runtime/diagnostic policy. Linux XDG behavior remains unchanged.
- `ManagedRuntimeIdentity` with explicit runtime type and installation/health state.
- `ComputeRuntime` boundary with `LocalLinuxRuntime` thin-adapting the existing local executor.
- `ManagedWSL2Runtime` placeholder returning `AVAILABLE_NOT_READY`; it performs no WSL subprocess, installation, or system mutation.
- Deterministic provider selection: Linux → local provider; Windows → managed WSL2 placeholder; other platforms remain unavailable through the same boundary.
- Optional execution provider provenance in `execution.json`; historical sidecars without it remain readable.
- Focused platform/path/provider/persistence tests.

## Explicitly unchanged

QE/EPW/Wannier90/Optical/Transport/Vibrational writers, parsers, compiler semantics, pseudopotential selection, ResultStore, Analyze, catalogue count, `.qs` schema, Builder, Device Builder, and Linux EngineFamily resolution were not changed for W1. No scientific engine was launched.

## Deferred to W2/W3

WSL availability/health probing, WSL installation and distro management, managed runtime tarball/Engine Pack installation, Windows packaging/installer, host↔runtime path translation, runtime repair/update, and scientific execution through WSL.
