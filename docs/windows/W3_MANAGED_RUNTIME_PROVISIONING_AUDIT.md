# W3 Managed QuantumStudioRuntime Provisioning Audit

## Scope and lifecycle

W3 provisions one private Windows WSL2 compute runtime with the lifecycle `ABSENT -> PROVISIONING -> REGISTERED -> RUNTIME_METADATA_VERIFIED -> INSTALLED_UNVERIFIED_SCIENCE`. It stops before Engine Pack verification and scientific execution. Registered or metadata-valid never means `SCIENTIFIC_RUNTIME_READY`.

## Host path and ownership

The only intended mutable host import root is `%LOCALAPPDATA%\QuantumStudio\runtime\wsl\QuantumStudioRuntime\`, derived from `backend.runtime.paths.RuntimePaths`. It is not Program Files, a source checkout, a project, Documents, or Desktop. Paths are passed to subprocess as distinct argv elements, so spaces and Unicode require no custom shell quoting.

After a successful import and metadata check, W3 writes `quantumstudio-runtime-host.json` into that directory. The marker records its own schema, exact runtime identity/version, architecture, import root, source digest, and in-runtime image digest. It is written through temporary file, flush, fsync where available, and atomic replace. A non-empty directory without a valid marker is unknown content: import/recreate is blocked and no recursive deletion occurs.

## Plan and version decisions

`plan_runtime_provisioning` is mutation-free and returns a typed `RuntimeProvisioningPlan` with action, reason, diagnostics, desired identity/version, digest-verification outcome, and a `destructive` flag. Actions are `NO_ACTION`, `IMPORT_RUNTIME`, `VERIFY_RUNTIME`, `REPAIR_METADATA`, `RECREATE_RUNTIME`, `HOST_PREREQUISITE_REQUIRED`, and `BLOCKED`.

Runtime versions are independent of the desktop version and use `major.minor-runtime.revision`. Equal is current; a revision difference within equal major/minor is compatible; an older major/minor requires explicit replacement; a newer major/minor is blocked rather than silently downgraded; malformed versions are invalid. Valid in-distro metadata with an absent/stale host marker is a non-destructive marker repair. WSL1, invalid metadata, and incompatible old foundations recommend destructive recreation rather than automatic removal.

## Commands and destructive safety

`ManagedWSL2CommandInterface` is deliberately non-generic. Its only operations are:

- `wsl.exe --import QuantumStudioRuntime <installation-root> <rootfs> --version 2`
- `wsl.exe --unregister QuantumStudioRuntime`
- fixed metadata read using `--distribution QuantumStudioRuntime --exec cat /opt/quantumstudio/runtime/runtime.json`

The existing injectable runner supplies structured argv, `shell=False`, captured output, and an explicit bounded timeout. No PowerShell, cmd shell string, `os.system`, WSL installation, DISM, registry operation, UAC flow, network access, user distro command, engine executable, or generic unregister API exists in W3.

Recreation carries `destructive=True` in its plan and its executor refuses it unless `allow_destructive=True`. Passive health inspection never unregisters anything. An import failure triggers fresh W2 discovery: partial registration is reported but never automatically unregistered.

## Post-import and idempotency

Successful `--import` is insufficient. W3 reruns W2 discovery, requires the exact distro at WSL2, reads fixed runtime metadata, validates it, then writes host ownership metadata. Missing/malformed metadata, identity/schema mismatch, WSL1, timeout, command failure, missing rootfs, digest mismatch, and unavailable WSL are controlled typed results.

An already current, marker-backed runtime plans `NO_ACTION`; a second `ensure_managed_runtime` neither imports, unregisters, destroys data, nor changes scientific state. User Ubuntu/Debian/Kali/Docker and similarly named distros remain discovery-only data and are never targets.

## Non-goals

W3 does not install WSL/Windows optional features, build an installer, create production images, install/verify Engine Packs, configure paths or pseudopotentials, translate host paths, stage/collect artifacts, execute/cancel science, alter `.qs`, or modify Builder, Device Builder, Analyze, ResultStore, QE, EPW, Wannier, BoltzTraP2, optical, transport, or vibrational semantics.

## Validation boundary

Automated tests inject Windows platform identity, W2 discovery, filesystem roots, and the WSL command runner on Linux. They contain only tiny rootfs fixtures and make no network or real WSL calls. Real Windows import remains an integration validation gate.
