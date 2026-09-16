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
