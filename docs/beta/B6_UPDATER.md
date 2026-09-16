# B6 updater

## Trust model

The update client trusts an Ed25519 signature, not a filename, release host,
or GitHub authentication.  It uses a key ring keyed by `kid`; update public
keys are a separate deployment input from licence signing keys, device keys,
and authentication keys.  No update private key belongs in this repository or
desktop build.

Canonical signatures use UTF-8 JSON, sorted keys, compact separators,
`ensure_ascii=False`, and `allow_nan=False`.  The manifest signature covers
all top-level fields except `signature`.  Each artifact signature covers all
artifact fields except `signature`, including `kid`.  This is deliberately
implemented in `backend.update.signing`, not reused from licensing.

## Manifest and selection

Schema 1 contains a selected `beta` or `stable` channel, release version,
publication data, application records for `windows-x86_64` and
`linux-x86_64`, and an optional Linux/x86_64 Engine Pack record.  Every record
has a filename, HTTPS URL, byte size, SHA-256, Ed25519 signature, type,
platform, and architecture.  Engine records also declare version and runtime
schema compatibility.

The selected channel is stored at `update-settings.json` in normal Quantum
Studio configuration.  It is never silently changed.  A manifest from a
different channel, unknown schema/key, wrong platform, malformed version,
invalid signature, or non-newer version is rejected.  Normal update handling
does not downgrade the installed application.

## Transport and staging

`HttpsUpdateSource` accepts only absolute HTTPS URLs and rejects redirects.
`FileUpdateSource` is explicitly test-only.  The client has a short timeout;
network and parse failures leave the application usable.

Artifacts are written below the managed cache `updates/<version>/` directory:
`%LOCALAPPDATA%\QuantumStudio\cache\updates` on Windows and
`$XDG_CACHE_HOME/QuantumStudio/updates` on Linux.  Download first writes
`*.partial`, checks size and SHA-256 after the signed metadata has been
validated, then uses an atomic replace.  A partial file is never installable.
Completed local state records only channel, check time, result, version, and
artifact hash; it contains no credential or project material.

## Installation handoff

On Windows a verified `windows-installer` is launched with structured argv and
Inno silent/update-safe flags only after the GUI has arranged normal shutdown.
The updater never edits running Program Files in place.  On Linux the initial
AppImage adapter returns the verified staged artifact for explicit user
replacement/launch; it will not overwrite an arbitrary executing AppImage.

Startup schedules a non-blocking check after the main window is visible.
`Help → Check for Updates` provides an interactive check.  Before an approved
endpoint and public key ring are configured, both behave as a safe no-update
state.  Future update UI work can add download/install progress without
changing the signed core contract.
