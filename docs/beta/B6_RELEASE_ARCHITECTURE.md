# B6 release architecture audit

## Initial assessment (2026-09-16)

This document records the implementation baseline before B6 changes.  It is
intentionally an audit of the checked-out source, not a claim that a public
release has been published.

### Repository state

- Branch: `beta-hardening-v0.2`
- Starting commit: `59200d722f6c8e0d2bb8bbfcb2e11ca546018a3d`
- Worktree: clean
- Canonical desktop version at the baseline: `0.2.0` in
  `backend.runtime.identity`.

### Existing Windows delivery and runtime work

- `scripts/build_windows.py` creates the W6 Nuitka standalone application
  plan/build and records build metadata.
- `scripts/build_windows_installer.py` generates a minimal Inno Setup 6
  script and invokes `ISCC.exe` through structured subprocess arguments.  It
  currently builds the application installer but does not yet model a signed
  cross-platform release manifest or an updater invocation contract.
- `scripts/windows_installer/` already provides a typed installer profile,
  atomic installer journal under ProgramData, reboot/resume state machine, and
  preservation-first uninstall contract.  This is retained rather than
  replaced.
- `backend.runtime.provisioning`, `wsl`, and `runtime_image` manage only the
  exact WSL2 distribution `QuantumStudioRuntime`.  They use fixed commands,
  structured argv, verified rootfs metadata, an ownership marker, and block
  destructive work on unknown ownership.  Existing user distributions are
  discovery-only and must remain so.
- `backend.runtime.engine_pack` already validates a versioned Linux/x86_64
  Engine Pack manifest and binary hashes; its immutable install/activation
  boundary is the foundation for the B6 Engine Pack release artifact.
- `runtime_agent/` and `backend.runtime.execution_bridge` provide the existing
  managed-runtime control protocol.  B6 must not expose WSL commands across
  application/scientific layers.

### Existing cross-platform and security foundations

- `backend.runtime.paths` already respects Windows AppData/LocalAppData and
  Linux XDG config/data/cache conventions.  B6 will add a dedicated
  per-version update staging root below these managed locations.
- The code base has no application-update client or authoritative release
  manifest.  Existing manifests concern scientific workflows, runtime images,
  and licensing rather than software publication.
- Licensing already uses Ed25519 canonical JSON verification.  B6 will use a
  separate update-signing namespace, keys, models, and verifier; it must never
  share licence keys or identities.
- No committed GitHub Actions workflow directory exists at this baseline.
- No Linux GUI package/AppImage build implementation exists at this baseline.
- No production private signing material was found in the audited release and
  runtime paths.  Production publication will require externally supplied
  signing material and will fail closed when it is absent.

### B6 target decisions

One signed, versioned release manifest is authoritative for both platform
records.  The manifest contains separate Windows and Linux application
artifacts and may reference one compatible Linux/x86_64 Engine Pack.  The
desktop, Engine Pack, runtime protocol/schema, and manifest schema remain
independently versioned.  Clients use HTTPS transport plus Ed25519 verification
and SHA-256; filenames and hosting provider trust are not update authority.

The first B6 implementation keeps public product version `0.2.0` until a
release tag is deliberately selected.  Local release/dry-run builds may carry
their explicit build generation without publishing or changing the public
release version.

## Audit follow-up

This assessment will be updated with the concrete B6 modules, tests, build
artifacts, validation evidence, and remaining physical validation gates as
they are implemented.

## Implemented B6 boundary

`backend.release` is the canonical source for the application version, Engine
Pack default, runtime schema, manifest schema, and default channel.  The
existing runtime identity imports the app version from that source, so Windows
and Linux package plans report the same value.  A future tag workflow validates
that `v<version>` exactly matches this source before it can publish.

`backend.update` now provides strict manifest models/parsing, separate Ed25519
signing and key-ring verification, HTTPS and test-only file transports, atomic
staging, explicit update states/failures, channel persistence, and Windows/
Linux installation handoff adapters.  `frontend.app.update_actions` exposes an
asynchronous startup check and `Help → Check for Updates` without coupling the
GUI to WSL or scientific execution.  The endpoint/key-ring remains deliberately
unconfigured until production public-key material and hosting are approved.

`scripts/build_release.py` produces a shared release directory containing both
application artifacts, an optional compatible Engine Pack, signed manifest,
signature sidecar, checksums, notes, and provenance.  Production signing fails
without injected material.  `scripts/build_linux_appimage.py` performs a real
Linux-host-only AppImage build and refuses to pretend Windows produced Linux.
The tag-only workflow builds both platforms, assembles the manifest only when
both succeed, and keeps publication draft-gated.
