# Quantum Studio Windows Runtime Architecture

Quantum Studio’s Windows beta goal is a native Windows desktop application that reaches **zero-configuration scientific execution** through a Quantum-Studio-managed WSL2 runtime. Users should not need to install Python, Quantum ESPRESSO, EPW, Wannier90, BoltzTraP2, Conda, Ubuntu, or configure environment variables manually.

The application and scientific runtime are separate concerns:

- `EngineFamily` identifies a coherent set of scientific executables and versions.
- `ComputeRuntime`/`ExecutionProvider` identifies where and how those executables run.
- `ResultStore` remains application-side; providers collect declared artifacts and existing parsers persist results.
- Host paths and future runtime paths are distinct. A Windows project path is not serialized as a Linux/WSL path.

W1 introduced Qt-free platform identity, Windows user-writable path policy, managed-runtime identity/state, and provider selection. W2 adds read-only host-level WSL discovery. Linux continues to use the existing `LocalExecutionManager` through a thin adapter. Windows selects a managed WSL2 provider that remains not-ready until later provisioning and verification. W3 adds deterministic offline provisioning and runtime-metadata verification, while the provider still refuses all scientific execution.

No user Ubuntu installation, Conda environment, arbitrary PATH executable, or external runtime is implicitly adopted by this boundary.

## W3 managed provisioning boundary

W3 consumes a local, SHA-256-verified WSL-importable rootfs descriptor and manages one exact distro identity: `QuantumStudioRuntime`. Its mutable host import root is `%LOCALAPPDATA%\QuantumStudio\runtime\wsl\QuantumStudioRuntime\`, obtained through `RuntimePaths` rather than a constructed username or source path. It writes an atomically replaced ownership marker only after the managed distro has passed post-import metadata verification.

The provisioning flow is plan-first: inspect W2 discovery, verify the image, inspect fixed in-distro metadata only for the exact managed distro, produce an explainable typed plan, then execute only that plan. Import uses structured `wsl.exe --import QuantumStudioRuntime <root> <rootfs> --version 2`; controlled recreation uses only `wsl.exe --unregister QuantumStudioRuntime` and requires caller authorization. User distros are never adopted or mutated.

Metadata lives at `/opt/quantumstudio/runtime/runtime.json`. It identifies the runtime version independently from the desktop version, metadata schema, architecture, build identity, and rootfs image digest. Metadata validation makes a runtime provisioned/verified, never scientifically ready. Runtime system content is intended for `/opt/quantumstudio`, while replaceable scientific user data will live separately under `/var/lib/quantumstudio`.

## Deferred

WSL installation, Engine Pack provisioning into WSL, host↔runtime path translation, Windows installer, Nuitka Windows build, registry/UAC integration, workflow staging/collection, and scientific execution through WSL remain future work. W3 does not install Windows features, run `wsl.exe --install`, execute engines, or bundle third-party scientific binaries.
## W2 discovery boundary

The canonical managed distribution identity is exactly `QuantumStudioRuntime`. W2 invokes only host-level `wsl.exe --list --verbose` and optional `wsl.exe --version` information probes through structured, `shell=False`, timeout-bounded calls. It never starts a distro or executes a command inside one. User distributions are diagnostic data only and are never adopted.

Registered WSL2 means only that the exact managed identity exists with WSL generation 2. It is not a scientifically verified runtime and is not exposed as ready for execution. Discovery state is host diagnostics, not `.qs` project state.
