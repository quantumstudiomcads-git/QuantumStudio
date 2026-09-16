# B6 release process

The current canonical app version is `0.2.0`; B6 does not change it
speculatively.  Before a real release, update `backend/release.py` through the
normal reviewed version-policy change so it exactly matches the intended tag,
for example `0.2.1-beta.1` and `v0.2.1-beta.1`.

Ordinary branch pushes run validation only.  A deliberate tag push triggers
the release workflow:

1. Build and audit the Windows standalone application and Inno installer on a
   Windows runner.
2. Build the Linux/x86_64 AppImage on a Linux runner; Windows never fakes this
   artifact.
3. Require the external Actions secrets
   `QUANTUM_STUDIO_UPDATE_SIGNING_KEY` and
   `QUANTUM_STUDIO_UPDATE_SIGNING_KID`.
4. Generate checksums, provenance, per-artifact signatures, and the common
   manifest only after both platform artifacts exist.
5. Upload artifacts, then upload the signed manifest last.  The release stays
   a draft for human approval.

For local validation, provide two non-production files and run
`python scripts/build_release.py --dry-run --version 0.2.1-beta.1 --channel beta --base-url https://updates.example.invalid/beta/0.2.1-beta.1 --windows-artifact <installer.exe> --linux-artifact <appimage> --output dist/releases/0.2.1-beta.1`.
It creates an ephemeral test key only in memory and prints its public half for
a test client.  Production mode fails closed without externally injected
signing material.

No real tag, hosting upload, or public update is part of B6 implementation.
