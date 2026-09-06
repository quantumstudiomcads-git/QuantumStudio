# Quantum Studio Windows Runtime Architecture

Quantum Studio’s Windows beta goal is a native Windows desktop application that reaches **zero-configuration scientific execution** through a Quantum-Studio-managed WSL2 runtime. Users should not need to install Python, Quantum ESPRESSO, EPW, Wannier90, BoltzTraP2, Conda, Ubuntu, or configure environment variables manually.

The application and scientific runtime are separate concerns:

- `EngineFamily` identifies a coherent set of scientific executables and versions.
- `ComputeRuntime`/`ExecutionProvider` identifies where and how those executables run.
- `ResultStore` remains application-side; providers collect declared artifacts and existing parsers persist results.
- Host paths and future runtime paths are distinct. A Windows project path is not serialized as a Linux/WSL path.

W1 introduces Qt-free platform identity, Windows user-writable path policy, managed-runtime identity/state, and provider selection. Linux continues to use the existing `LocalExecutionManager` through a thin adapter. Windows selects a managed WSL2 provider that reports not-ready.

No user Ubuntu installation, Conda environment, arbitrary PATH executable, or external runtime is implicitly adopted by this boundary.

## Deferred

WSL detection, installation, distro import, Engine Pack provisioning into WSL, runtime repair/update, Windows installer, Nuitka Windows build, registry/UAC integration, and scientific execution through WSL are W2/W3 work.
