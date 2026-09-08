# W7 — Unified zero-config Windows installer audit

## Scope

W7 adds a testable installer orchestration boundary, not a real Windows build
claim. Scientific input generation, parser behavior, ResultStore, `.qs`, the
147-entry catalogue, and all Linux scientific execution remain untouched.

## Implemented boundary

- `scripts/windows_installer/contracts.py` validates the W6 application
  manifest, W3 local runtime image digest, and W5 Engine Pack manifest,
  platform, architecture, and per-file hashes before install phases.
- `state.py` persists a schema-versioned atomic ProgramData journal and safe
  reboot-resume state.
- `orchestrator.py` contains the typed state machine and injected component
  backend, so normal tests need no Windows, WSL, privilege, registry, or reboot.
- `system.py` contains the sole fixed Windows prerequisite argv construction.
  It has no arbitrary feature, shell, or user-controlled command interface.
- `runtime_adapter.py` calls W3/W5 contracts and maps unrecognized runtime
  ownership to a blocked installer outcome. It never authorizes recreation.
- `payload_audit.py` rejects test/source/venv content and undeclared rootfs/VHDX
  payloads. Declared local payloads can be delivered offline.
- `build_windows_installer.py` selects Inno Setup 6 and supports cross-platform
  plan mode; compilation refuses non-Windows hosts.

## Safety policy

The installer owns exactly `QuantumStudioRuntime`. User distros cannot be
selected through any API. Normal uninstall preserves runtime scientific data
and all `.qs` projects. Full cleanup is explicit-confirmation-only and must
remain ownership-verified in the Windows helper. The GUI remains unelevated and
does not provision at first launch.

## Pending physical gates

`PENDING_REAL_WINDOWS`: Setup.exe creation, UAC behavior, Windows feature
changes, reboot/resume registration, WSL import, runtime agent health, Engine
Pack activation, actual uninstall/repair/upgrade, and all W8 scientific runs.

Code signing is **PENDING**. Public Engine Pack distribution/legal review is
**PENDING**. W7 does not create or commit installer EXEs, rootfs images, Engine
Packs, or scientific binaries.
