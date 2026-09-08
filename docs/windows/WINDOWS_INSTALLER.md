# Quantum Studio Windows installer

W7 specifies an offline-first Windows 11 x64 installer architecture. The native
application, `QuantumStudioRuntime`, and the Scientific Engine Pack remain
separate components. The installer is the only component allowed to perform
privileged host preparation; `QuantumStudio.exe` remains a normal standard-user
application and never self-provisions WSL, imports a runtime, or installs an
Engine Pack.

## Toolchain and build

The selected compiler is **Inno Setup 6**, a free/open-source, scriptable
Windows installer system. `scripts/build_windows_installer.py --plan` is safe
on any platform and reports an installer plan. A real build requires Windows,
a verified W6 standalone bundle, and a locally installed `ISCC.exe`/`iscc`; it
refuses to claim a build on Linux. The compiler is called with structured argv
and `shell=False`. Installer outputs belong under `dist/windows-installer/` and
are generated artifacts, never source-controlled. Code signing is **PENDING**.

The installer build profiles are `GUI_ONLY`, `GUI_PLUS_RUNTIME`, and
`FULL_SCIENTIFIC`. This supports a legal-gated local Engine Pack payload without
claiming that third-party scientific binaries are approved for public
redistribution.

## State, privileges, and reboot

`scripts/windows_installer/state.py` has a schema-versioned, atomically written
journal. On Windows it is stored under
`%PROGRAMDATA%\QuantumStudio\installer\installer-state.json`, not the working
directory or a temporary directory. It records typed phases, timestamps,
diagnostics, rollback notes, and whether a controlled resume entry is active.
Corrupt state is a repair condition rather than a reason to guess or restart.

The state machine checks host compatibility, checks/enables prerequisites,
handles reboot/resume, installs/verifies the app, imports/verifies the runtime,
installs/verifies the Engine Pack, creates shell integration, and finalizes.
Only an installer helper would elevate through standard Windows UAC; no password
is collected or stored. The normal app is not elevated.

Windows prerequisite detection is read-only. The only mutating prerequisite
commands prepared by W7 are fixed `dism.exe /online /enable-feature` argv for
`Microsoft-Windows-Subsystem-Linux` and `VirtualMachinePlatform`, with
`/norestart`. Reboot is requested only when the documented command returns its
reboot code. There is no general shell, `cmd.exe /c`, user-interpolated
PowerShell, registry hack, network download, package manager, or automatic
WSL install call.

## Runtime and Engine Pack

Only the exact identity `QuantumStudioRuntime` is installer-owned. W3 remains
the runtime import authority and uses a verified local rootfs descriptor before
its fixed `wsl.exe --import ... --version 2` operation. Existing Ubuntu, Debian,
Kali, Docker Desktop, and similarly named distros are never selected or
modified. If the exact name exists but W3 ownership metadata is invalid, the
installer records an ownership conflict and blocks destructive action.

The W7 adapter maps W3 typed results rather than bypassing them. It does not
authorize runtime recreation; full recreation or removal requires an explicit
later installer policy and ownership proof. W5 remains the Engine Pack
authority: W7 requires the manifest SHA-256 and per-tool/platform/architecture
validation before deployment, and W5 verifies again before atomic activation.
Previous known-good Engine Packs are retained by W5. **PUBLIC ENGINE PACK
DISTRIBUTION LEGAL REVIEW: PENDING.**

## Install, repair, upgrade, and removal

Inno Setup installs the W6 bundle under `{autopf}\QuantumStudio`, creates a
Start Menu shortcut, and supplies the ordinary Windows uninstall entry. The
bundle is read-only at runtime; mutable app/runtime data stays in the existing
APPDATA/LOCALAPPDATA policy.

A rerun verifies current components and uses no-op actions where possible.
Repair is component-specific: app, runtime metadata/agent, and Engine Pack are
separate. A compatible runtime's mutable scientific state is not recreated as
an upgrade shortcut. Failed app/runtime/Engine Pack work stays journaled for
repair and never activates unverified components.

Normal uninstall removes the app and shell integration only. It preserves user
`.qs` projects everywhere and preserves `QuantumStudioRuntime` plus scientific
runtime data by default. Full runtime/cache removal requires explicit
confirmation, exact ownership validation, and targets only
`QuantumStudioRuntime`; it never removes another distro or scans for projects.

## Physical validation still required

Real Windows 11 x64 build, UAC, feature enablement, reboot/resume, runtime
import, Engine Pack installation, repair/upgrade/uninstall, signing, and W8
scientific parity are **PENDING_REAL_WINDOWS**. The Linux test suite exercises
only synthetic payloads and mocked system operations.
