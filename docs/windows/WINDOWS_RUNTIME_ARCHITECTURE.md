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

W4 adds a synchronous, fixed-endpoint runtime-agent control bridge. It can execute only a typed task whose executable, working directory, and I/O paths already exist inside the managed runtime. Host-to-runtime staging, artifact collection, Engine Pack installation, scientific workflow execution, cancellation, and recovery remain future work. W3/W4 do not install Windows features, run `wsl.exe --install`, execute engines during provisioning, or bundle third-party scientific binaries.
## W2 discovery boundary

The canonical managed distribution identity is exactly `QuantumStudioRuntime`. W2 invokes only host-level `wsl.exe --list --verbose` and optional `wsl.exe --version` information probes through structured, `shell=False`, timeout-bounded calls. It never starts a distro or executes a command inside one. User distributions are diagnostic data only and are never adopted.

Registered WSL2 means only that the exact managed identity exists with WSL generation 2. It is not a scientifically verified runtime and is not exposed as ready for execution. Discovery state is host diagnostics, not `.qs` project state.


## W5 managed scientific-runtime boundary

W5 keeps three separate products: the native Quantum Studio application, the private `QuantumStudioRuntime` WSL appliance, and a separately versioned Scientific Engine Pack. An Engine Pack is a local/offline artifact with `engine-pack.json`, a platform/architecture identity, per-tool SHA-256 hashes, and a manifest digest supplied by the caller. It is verified before installation, copied to a versioned `packs/<pack-id>-<version>` location, verified again, then activated by atomically replacing `active.json`. The installation root carries a Quantum Studio ownership marker; non-empty unmarked roots and same-version/different-digest conflicts are blocked. Previous packs are retained, and silent downgrade is refused.

Verified manifest entries map a logical tool ID directly to an absolute runtime POSIX path under `/opt/quantumstudio/engines`; managed execution never searches ambient `PATH`. A complete runtime additionally requires WSL2 registration, W3 metadata, a compatible W4 agent, a valid Engine Pack and required tool/capability mapping. This is distinct from a claim that every optional scientific capability is installed.

W5 transfer operations are narrow runtime-agent operations: `stage-in` streams a declared host file into a trusted runtime root via a temporary file, SHA check, and atomic replace; `stage-out` streams one declared trusted runtime file to an atomically replaced host destination. There is no `/mnt/c` conversion, recursive project copy, generic file API, or bulk JSON/base64 transport. Runtime work is placed beneath `/var/lib/quantumstudio/workflows/<workflow-id>/executions/<execution-id>/<task-id>/`; large scratch/restart data stays there. Exact selected pseudopotential bytes and SHA remain host-selected and may later be cached by SHA beneath `/var/lib/quantumstudio/pseudopotentials`.

The runtime agent now records managed task IDs, PID/PGID, start discriminator, executable and cwd in atomically written records under `/var/lib/quantumstudio/runtime/tasks`. `status` and `cancel` accept a validated task ID only. Cancellation signals the recorded owned process group with SIGTERM, then SIGKILL after a grace period; it never accepts a host-provided PID. Recovery does not rerun tasks; a missing/non-live owned task is interrupted unless durable terminal evidence exists.

### Managed process cancellation ownership

On Windows, each managed launch creates a named Job Object and configures
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` before process creation. It then calls the
documented `CreateProcessW` API with `CREATE_SUSPENDED` and
`CREATE_NEW_PROCESS_GROUP`, using `STARTUPINFOEX` with a restricted standard
handle list so unrelated inheritable handles are not passed to the child. The
returned primary-thread and process handles are non-inheritable. The suspended
process is assigned to the Job Object and verified with its process creation
time and job membership before the retained primary-thread handle is resumed
with documented `ResumeThread`. If creation, assignment, or resume fails, the
launching code terminates and reaps only that suspended process/job and closes
the handles it owns.

The Job Object is the owned process-tree boundary; the launcher PID alone does
not represent every interpreter or descendant. The task record binds the job
name to a random ownership token and records the launched process creation
time. The execution thread retains the original Job Object handle for the
task lifetime. Cancellation opens a temporary handle to that same named job,
checks the token, process creation identity and job membership, and closes only
its temporary handle. The job remains reopenable while its execution-owner
handle is open; that final owner handle triggers `KILL_ON_JOB_CLOSE` when the
task finishes. Job and process handles are not inherited by the child.

Cancellation sends `CTRL_BREAK_EVENT` only to the explicitly created,
nonzero child group after verifying membership. It rereads the authoritative
task record during bounded grace polling and before each termination or final
state update. If the graceful request is unavailable or ignored, it terminates
the token-bound Job Object and waits with a bounded deadline. Terminal state
wins over a stale cancellation snapshot; repeated and concurrent requests do
not signal again. No process-name-based termination is used.

POSIX launches retain their separate session and process-group behavior, with
the process start discriminator and group checked before signalling. On both
platforms, task-record transitions are serialized. Cancellation rereads the
authoritative state before escalation, stops when the task is terminal, and
allows only one cancellation request to own the bounded grace/termination
sequence. Natural completion is preserved if it wins the race. Job/process
waits are bounded, and repeated cancellation is idempotent; unrelated
processes remain outside the managed ownership boundary.

Result parsing remains host-side: only collected host paths are handed to `ResultService` and `ResultStore`, so Analyze can show persisted results without WSL. W5 preserves the existing distinction between a zero process exit (`COMPLETED`) and parser result validity (`PARSE_FAILED` is not an engine failure).

PUBLIC ENGINE PACK DISTRIBUTION LEGAL REVIEW: **PENDING**. W5 contains no third-party engine binaries, no downloader, no package-manager calls, and no real Windows/QE validation.


## W6 application bundle boundary

W6 adds a Windows-only Nuitka standalone build plan, centralized source/frozen resource discovery, and writable APPDATA/LOCALAPPDATA application roots. The application bundle is read-only at runtime and excludes Engine Packs, rootfs/VHDX payloads, scientific engines, tests and source-checkout artifacts. Startup is offline and remains usable when WSL, the managed distro, metadata or Engine Pack are absent. A read-only JSON integration harness performs no provisioning or scientific execution. Native Windows build, signing and installer composition remain physical future gates.


## W7 installer boundary

W7 adds an installer-only, offline-first orchestration layer. It uses a typed,
atomically journaled state machine beneath `%PROGRAMDATA%\QuantumStudio\installer`
for host checks, optional fixed prerequisite enablement, reboot/resume, W6 app
installation, W3 runtime import/verification, W5 Engine Pack verification, and
shell integration. `QuantumStudio.exe` remains a standard-user app and does not
self-provision on launch. The only managed distro is exactly
`QuantumStudioRuntime`; ownership conflicts block destructive work and user
distros remain untouched. Normal uninstall preserves `.qs` projects and runtime
scientific data; full cleanup requires explicit confirmation and ownership
verification. Inno Setup 6 is the planned Windows compiler; actual compilation,
UAC/reboot behavior, and all real runtime/scientific validation remain
**PENDING_REAL_WINDOWS**. Public Engine Pack distribution/legal review and code
signing remain pending.
