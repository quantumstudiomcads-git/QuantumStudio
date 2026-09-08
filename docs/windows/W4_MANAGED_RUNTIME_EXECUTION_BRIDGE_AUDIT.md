# W4 Managed QuantumStudioRuntime Execution Bridge Audit

## Scope

W4 adds a synchronous control plane between the Windows application and the exact managed `QuantumStudioRuntime` WSL2 distribution. It is engine-neutral infrastructure, not an Engine Pack, calculation adapter, workflow stager, artifact collector, ResultStore integration, or Windows GUI change.

## Agent and protocol

The first-party, standard-library-only `runtime_agent` package is installed by a future rootfs builder at `/opt/quantumstudio/runtime/bin/qs-runtime-agent`. It imports no Qt, frontend, NumPy, or scientific engine code. Its JSON protocol has independent schema version `1` and agent version `1`.

The host accepts a typed task containing a task ID, absolute POSIX runtime executable, argv array, runtime cwd, explicit environment map, optional runtime-local stdin/stdout/stderr paths, and optional explicit timeout. No commands are shell strings. The agent writes JSON-only control responses containing status, exact return code, PID, process group, timestamps, duration, and a bounded diagnostic.

## Exact WSL boundary

The only host invocation shapes are:

- `wsl.exe --distribution QuantumStudioRuntime --exec /opt/quantumstudio/runtime/bin/qs-runtime-agent health`
- `wsl.exe --distribution QuantumStudioRuntime --exec /opt/quantumstudio/runtime/bin/qs-runtime-agent run`

Task JSON travels over stdin for `run`; the response is small JSON on stdout. Calls use structured argv, `shell=False`, captured output, and an explicit short control timeout for health. Task transport has no artificial short timeout; an optional request timeout is enforced by the agent. The host retains Linux PID/PGID returned by the agent for W5 cancellation design, rather than assuming a Windows `wsl.exe` PID is sufficient.

There is no API parameter for a distro identity. Ubuntu, Debian, Docker, similarly named distributions, and all user distros are structurally untargetable.

## Runtime safety policies

Runtime paths are absolute POSIX strings only: no host `C:` drive paths, relative paths, NUL bytes, or backslashes. W4 never translates a host path into `/mnt/c`; host and runtime namespaces stay distinct.

The agent accepts executables only below `/opt/quantumstudio/engines` or `/opt/quantumstudio/runtime/bin`, and working/I/O paths only below `/var/lib/quantumstudio/workflows` or `/var/lib/quantumstudio/staging`. Tests inject temporary trusted roots without weakening production defaults. The agent starts `[executable, *argv]` using `subprocess.Popen(shell=False, start_new_session=True)`.

The environment starts from a minimal runtime baseline (`PATH` and `LC_ALL`) plus validated explicit string-to-string overrides. It never forwards the Windows environment. Absent stdin uses `DEVNULL`; optional stdin/stdout/stderr must already be runtime-local trusted paths. Large output never crosses the JSON control channel.

## Readiness and provenance

Managed execution requires a Windows host, successful exact WSL2 discovery, W3 metadata validity, and a compatible agent health response. It never auto-provisions during Run. A runtime with a working bridge is still not scientifically ready: no Engine Pack is installed or verified.

Provider provenance can record managed WSL2, `QuantumStudioRuntime`, independent runtime version, Linux runtime platform/architecture, and agent protocol/version. Older records retain their optional empty provenance unchanged.

## Deferred

W5 owns Engine Pack install/discovery, host-to-runtime input and pseudopotential staging, runtime-to-host artifact collection, cancellation by recorded Linux process group, interrupted-task recovery, execution sidecar integration, and ResultStore parsing after collection. Real Windows/WSL bridge validation is also deferred; W4 automated tests use direct local agent execution and mocked WSL transport on Linux. No scientific executable is run by W4 tests.
