# Quantum Studio Windows Runtime Architecture

Quantum Studio’s Windows beta goal is a native Windows desktop application that reaches **zero-configuration scientific execution** through a Quantum-Studio-managed WSL2 runtime. Users should not need to install Python, Quantum ESPRESSO, EPW, Wannier90, BoltzTraP2, Conda, Ubuntu, or configure environment variables manually.

The application and scientific runtime are separate concerns:

- `EngineFamily` identifies a coherent set of scientific executables and versions.
- `ComputeRuntime`/`ExecutionProvider` identifies where and how those executables run.
- `ResultStore` remains application-side; providers collect declared artifacts and existing parsers persist results.
- Host paths and future runtime paths are distinct. A Windows project path is not serialized as a Linux/WSL path.

W1 introduced Qt-free platform identity, Windows user-writable path policy, managed-runtime identity/state, and provider selection. W2 adds read-only host-level WSL discovery. Linux continues to use the existing `LocalExecutionManager` through a thin adapter. Windows selects a managed WSL2 provider that remains not-ready until later provisioning and verification.

No user Ubuntu installation, Conda environment, arbitrary PATH executable, or external runtime is implicitly adopted by this boundary.

## Deferred

WSL installation, distro import, Engine Pack provisioning into WSL, runtime filesystem verification, runtime repair/update, host↔runtime path translation, Windows installer, Nuitka Windows build, registry/UAC integration, and scientific execution through WSL remain W3+ work.
## W2 discovery boundary

The canonical managed distribution identity is exactly `QuantumStudioRuntime`. W2 invokes only host-level `wsl.exe --list --verbose` and optional `wsl.exe --version` information probes through structured, `shell=False`, timeout-bounded calls. It never starts a distro or executes a command inside one. User distributions are diagnostic data only and are never adopted.

Registered WSL2 means only that the exact managed identity exists with WSL generation 2. It is not a scientifically verified runtime and is not exposed as ready for execution. Discovery state is host diagnostics, not `.qs` project state.
