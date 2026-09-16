# B6 validation

Automated B6 coverage includes version/channel comparison, strict manifest
parsing, Ed25519 canonical verification, tampered signature rejection,
checksum mismatch, wrong-platform selection, anti-downgrade behavior, atomic
partial staging, shared Engine Pack selection for Windows/Linux, and a local
dry-run release generator that emits both platform records.

Physical acceptance remains required before public beta release:

- clean Windows 11 x64 fresh install, upgrade, repair, normal uninstall, and
  explicit full runtime removal;
- WSL unavailable/enabled/reboot-required states, existing user distros,
  interrupted managed import, and managed-runtime health;
- Linux x86_64 AppImage launch, project open/save, Builder/Calculate entry,
  native runtime discovery, and verified update handoff on the declared base
  distribution;
- Authenticode signing (currently `AUTHENTICODE_PENDING`) and approved Engine
  Pack legal notices.

Until these are completed, do not represent B6 as a fully accepted production
installer release.  No test or validation step should delete research data,
licensing identity, or an existing managed Engine Pack.

## B6.2 Windows standalone validation (2026-09-16)

The clean `593eacd4cabc17453d45458c35234ab833dd7b72` B6.2 standalone archive
was validated without changing its contents. Its embedded build manifest
identifies Quantum Studio `0.2.0` / `beta`, Python `3.13.15`, PySide6 `6.11.2`,
and Nuitka `4.1.1`. The extracted bundle contains 372 files / 503,216,913
bytes; `QuantumStudio.exe` SHA-256 is
`EB551F54388F8E17960CF39271F556DC7E8F8409141881349C0C8DF62E7C96EA`.

The existing package audit passed: executable, build/install manifests,
application asset, Qt `qwindows.dll`, Python runtime, and cryptography
`_rust.pyd` are present; no GUI-package Engine Pack, WSL rootfs, engine
executable, private key, or token was found. Process-level launch validation
passed for the original standalone location and fresh complete ordinary-path,
spaces-path, and Unicode-path copies: each remained alive for at least 12
seconds with empty stderr. The console-disabled catalogue smoke exited
successfully, while its printed payload is intentionally not capturable from a
Windows-console-disabled executable. Native GUI automation was unavailable, so
menu/dialog click-through remains an honest manual validation limitation.

Focused B6.2/B6.3 checks completed with `80 passed, 4 subtests passed`.

## B6.3 installer validation status (2026-09-16)

The generated Inno Setup source was statically inspected and is bound to the
same canonical `0.2.0` application version. It uses stable AppId
`{{C90FC580-47D1-4A00-9C12-8A4502DEB601}`, `{autopf}\QuantumStudio`, Start Menu
and optional desktop shortcuts, and Inno close/restart handling. The expected
updater handoff remains `/SP- /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
/CLOSEAPPLICATIONS`.

No Inno Setup 6 `ISCC.exe` compiler is installed or discoverable on this build
machine. Therefore no installer artifact, fresh install, upgrade, reinstall,
uninstall, or Authenticode validation has been claimed. B6.3 remains blocked
until an approved existing Inno Setup 6 toolchain is supplied; no workaround
or substitute installer was used.
