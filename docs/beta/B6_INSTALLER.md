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

The stable Inno Setup AppId is `{{C90FC580-47D1-4A00-9C12-8A4502DEB601}`. It
must remain unchanged across normal upgrades. ProgramData holds only the
installer continuation journal and runtime state under
`%PROGRAMDATA%\QuantumStudio\installer`; device identity and per-user licence
state remain in the existing user-scoped application paths.

As of B6.3 validation, the source has been reviewed but this host has no
discoverable `ISCC.exe`. Installer compilation and controlled fresh/upgrade/
reinstall/uninstall execution are consequently pending the approved Inno Setup
6 toolchain. This is a build-environment gate, not a reason to replace the
existing installer architecture.

## Verified customer payload boundary

The authoritative Windows standalone build writes
`quantumstudio-payload-inventory.json` only after the standalone payload,
`quantumstudio-build.json`, and `quantumstudio-installer-input.json` are
final. The versioned inventory lists every payload file except itself by
canonical forward-slash path, byte size, and lowercase SHA-256. The installer
builder rejects legacy/uninventoried bundles, compares the exact file set and
metadata, streams hashes, and runs path and content audits. It then creates a
unique operation-owned staging root beneath the dedicated installer output,
copies only inventoried files into a payload snapshot, hashes the copied
bytes, and re-audits that snapshot. The Inno script uses one explicit file
entry per inventory record; no wildcard or recursive source rule is used.
On Windows, read-only handles denying write and delete sharing are held for
inventoried files, snapshot directories where supported, and the temporary
`.iss` for the complete ISCC invocation. The snapshot is rechecked while
locked immediately before compilation. The completed installer is published
without replacing an existing output; the unique staging root is removed
after its ownership marker and identity are verified. A pre-existing final
`.iss` or installer is preserved and causes failure.
The inventory copy transfers only the ordinary file data stream; alternate
data streams are not copied or named by the generated source list.

These controls defend against concurrent filesystem changes to the original
bundle and controlled snapshot within the trusted builder process: original
changes after snapshot creation cannot affect compiler input, and extra
snapshot files are not named by the explicit Inno list. They do not defend
against arbitrary malicious code already running in the builder process,
compromise of the Windows build account, administrator/kernel control, or a
replaced ISCC executable. Windows directory sharing behavior can vary; the
explicit source list is the primary control against added files. The snapshot
is not cryptographically immutable.

Customer package audits do not trust filename extensions. They reject known
SQLite database/journal/WAL signatures, private-key PEM material, known
Licence Manager protected-key purpose/envelope fields, applicant/audit export
records, receipts, and pre-issued signed licences. ZIP-compatible and other
recognized archive/container formats are forbidden in customer bundles rather
than recursively unpacked. Linux AppImage staging reuses the content-sensitive
audit, but does not yet have the Windows canonical payload inventory format.

These checks detect known formats and verify the exact inventoried build
payload; they cannot classify every possible encrypted or arbitrary byte
sequence. Clean source control, build-host custody, and release provenance
remain part of the release trust boundary. Existing accepted artifacts are
not retrofitted by this change.

`QuantumStudioRuntime` is exactly the private WSL2 identity managed by the
existing W3 provisioner.  It uses the managed LocalAppData runtime root and a
fixed, structured `wsl.exe --import QuantumStudioRuntime ... --version 2`
operation.  It neither adopts nor mutates Ubuntu or any other user WSL distro.
Unknown runtime ownership blocks destructive work.  WSL/feature detection,
reboot state, rootfs validation, metadata validation, and resume state remain
the responsibility of the existing installer/runtime contracts.
