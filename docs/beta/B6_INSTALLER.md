# B6 Windows installer

Quantum Studio retains the W7 installer architecture rather than replacing it.
`scripts/windows_installer/` owns the schema-versioned atomic journal at
`%PROGRAMDATA%\QuantumStudio\installer`, host/prerequisite assessment,
reboot/resume state, and typed orchestration.  The Inno Setup 6 builder creates
a Windows 11 x64 installer for a verified W6 standalone bundle.

The installer uses Program Files (`{autopf}\QuantumStudio`), a stable AppId,
Start Menu shortcut, optional desktop shortcut, versioned uninstall entry, and
Inno application-close/restart support.  Update handoff arguments are:

`/SP- /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS`

Normal upgrades and uninstalls remove or replace application binaries only.
They preserve `.qs` projects, results, preferences, diagnostics, licensing
identity/leases, and `QuantumStudioRuntime`.  Full runtime removal is an
explicit confirmation-only orchestrator action; it is never the normal
uninstall path.

`QuantumStudioRuntime` is exactly the private WSL2 identity managed by the
existing W3 provisioner.  It uses the managed LocalAppData runtime root and a
fixed, structured `wsl.exe --import QuantumStudioRuntime ... --version 2`
operation.  It neither adopts nor mutates Ubuntu or any other user WSL distro.
Unknown runtime ownership blocks destructive work.  WSL/feature detection,
reboot state, rootfs validation, metadata validation, and resume state remain
the responsibility of the existing installer/runtime contracts.
