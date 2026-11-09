# Windows desktop build profiles and public runtime configuration

## Audit of the previous Windows pipeline

- `scripts/build_windows.py` drives native Windows x86_64 Nuitka standalone builds
  with PySide6/MSVC. It generates an icon, audits the GUI bundle and writes build,
  installer-input and hashed payload-inventory metadata. The installer is Inno Setup 6
  through `scripts/build_windows_installer.py`; it copies a verified inventory into
  an owned snapshot and compiles GUI_ONLY installers. Scientific runtime/Engine Pack
  delivery remains outside this GUI bundle's current supported installer mode.
- Runtime licensing previously read process `BETA_ENVIRONMENT`, `QS_WEBSITE_URL`
  and `QS_LICENCE_TRUST` only. Setting them in the compiler shell did not persist
  them in an installed executable. Local/staging/production validation existed,
  but there was no packaged profile/config file or executable-bound public pin.
- Local TEST trust was explicitly file-configured and never automatically bundled.
  Existing content audits excluded operator stores, preissued licences, private key
  formats, databases, dotenv files and other sensitive artifacts. Compiler subprocesses
  previously inherited the entire parent environment; that boundary is now filtered.
- Update configuration used environment-supplied endpoint/public keys and a shared
  per-user beta/stable preference. Signed channel/version/anti-downgrade checks existed,
  but deployment environments were not bound to feeds or artifact identities.
- Portable and installed copies both used the same standalone resource discovery.
  Both needed explicit persistent public configuration. The prior installer AppId,
  shortcut names and default directories did not distinguish staging from production.

## Explicit build profiles

The native build CLI now REQUIRES `--profile local|staging|production`. There is no
implicit deployment profile. Release `--channel` remains separate metadata (use
`beta` explicitly for the v0.2 closed beta); it does not choose licence environment.

- `packaging/windows/staging.json` contains the requested staging HTTPS origin and
  the committed approved staging public issuer/key. It contains no credentials.
- `packaging/windows/production.json` is deliberately incomplete: independent approved
  production origin/public trust are not provisioned. It FAILS validation as shipped.
  Supply a reviewed public-only production JSON via `--config`, or review/populate
  the public production template later. Do not copy/relabel staging or TEST trust.
- `--profile local` produces a local marker with no deployed trust or origin; local
  TEST opt-ins, explicit trust file and loopback settings remain separate runtime
  development configuration. `Start-QSWebsite`, `Start-QSLicenceManager`, source
  execution and `scripts/qs-local.ps1` are untouched.

The strict public JSON schema has exactly four fields:

```json
{
  "schema_version": 1,
  "environment": "production",
  "website_origin": "APPROVED_HTTPS_PUBLIC_ORIGIN",
  "licence_trust": {
    "schema_version": 1,
    "environment": "production",
    "domain": "licence",
    "algorithm": "Ed25519",
    "keys": {"lic-APPROVED-LOWERCASE-ISSUER": "APPROVED_CANONICAL_BASE64URL_PUBLIC_KEY"}
  }
}
```

Placeholders are intentionally invalid. Issuers follow the existing lowercase
`lic-...` contract. Each public key is canonical unpadded base64url of 32 raw bytes.
Missing/extra/duplicate fields, TEST trust, environment mismatch, local/insecure or
placeholder deployed origins, and empty/malformed trust fail closed. This is not a
secret store: additional fields, including credential bindings, are rejected.

## Packaged resource and precedence

For each build, only the selected public profile is canonicalized into
`quantumstudio-desktop.json`. A generated `_quantumstudio_packaged_profile` module
is COMPILED into that executable and pins the raw resource SHA-256, environment,
build channel/commit/timestamp. The generated Python source stays in build-assets,
not customer resources. Nuitka includes only this one JSON, not the directory of
staging/production source manifests. No private authority or website module is needed.

Startup locates the file beside the executable using existing packaged resource
discovery. It validates bounds/schema/encoding and compares its bytes to the
compiled digest/environment. Missing resource/pin, modified bytes or invalid trust
makes licensing configuration unavailable BEFORE device-key creation or network
use. Read-only application use follows existing policy. Nothing silently selects
local or downloads trust. Raw unknown configuration values are not logged.

For packaged staging/production, the resource is authoritative. The three public
process variables may be absent or match it; a conflicting value rejects the
configuration rather than redirecting/downgrading the app. Trust JSON whitespace
and member order may differ; duplicate keys are rejected. URL/environment strings
must match exactly. Existing TEST/HTTP flags remain prohibited. Runtime values are
combined in memory; startup does not write OS/process settings or a user secret file.

Source execution remains environment-driven and does not load arbitrary profile
files from the working directory. Packaged local mode preserves explicit local
TEST environment configuration. Existing user-selected data-root overrides remain
available. Default profiled staging/local roots are `QuantumStudio-Staging` and
`QuantumStudio-Local`; production keeps `QuantumStudio`. Thus device/cache/update
settings do not silently cross between ordinary packaged profiles. Do not manually
point profiles at the same mutable data root or copy DPAPI identities between users.
An earlier staging run using the old shared data root may require a normal replacement
activation; no device key is migrated/replaced automatically.

Both portable copies and Inno installations use the same executable-relative public
file, so they do not depend on the launcher's current directory or compiler environment.
Always copy the entire standalone directory for portable use. The installer inventories
and rechecks the selected public file/hash, and cannot retag the profile using its CLI.
Staging/local installers have distinct AppIds, install directories, shortcut names
and artifact filenames. Production retains its existing install identity.

The digest is integrity protection anchored in the executable, not independent
publisher authentication. Authenticode/approved distribution, installer signing and
key custody remain external release requirements; an attacker replacing the executable
can replace its code. No publisher key was generated or provisioned here.

## Updater boundary

New profiled packages currently have automatic updates DISABLED. No independently
approved environment-bound update feed/artifact contract exists yet. Both missing/
invalid profiles and valid profiled packages ignore external update endpoint/key
variables and shared user channel preferences. Staging cannot silently select
production artifacts, and production cannot select staging/dev artifacts. No bypass
switch was added. Manual updates must use the corresponding reviewed installer.

Source/development updater configuration remains unchanged. Existing signed manifest
channel checks, signature/digest checks, version ordering and anti-downgrade behavior
are untouched and covered by updater regressions. Enabling cloud updates in packaged
profiles requires a separate reviewed environment-bound feed/public-key/artifact
contract; this step deliberately does not redesign or provision that service.

## Exact commands (future real builds require a clean reviewed checkout)

Plan-only validation, no compilation/download/deployment:

```powershell
.\.venv\Scripts\python.exe scripts\build_windows.py --profile staging --channel beta --dry-run
.\.venv\Scripts\python.exe scripts\build_windows.py --profile production --channel beta --config C:\approved-public-config\production.json --dry-run
```

Staging native build and GUI installer:

```powershell
.\.venv\Scripts\python.exe scripts\build_windows.py --profile staging --channel beta
.\.venv\Scripts\python.exe scripts\build_windows_installer.py --profile GUI_ONLY --app-bundle dist\windows\QuantumStudio-0.2.0-staging-beta\main.dist --output dist\windows-installer-staging
```

Production native build and GUI installer, ONLY after approval of independent public
production values (the path below is a placeholder):

```powershell
.\.venv\Scripts\python.exe scripts\build_windows.py --profile production --channel beta --config C:\approved-public-config\production.json
.\.venv\Scripts\python.exe scripts\build_windows_installer.py --profile GUI_ONLY --app-bundle dist\windows\QuantumStudio-0.2.0-production-beta\main.dist --output dist\windows-installer-production
```

The installer `--profile GUI_ONLY` selects components; deployment environment is
inherited from the verified bundle, not selected by that argument. Nuitka can name
the output `.dist` directory according to its version; use the builder's reported
bundle path if it differs from `main.dist`. Real builds require Windows/MSVC/Nuitka,
PySide6 and Inno Setup, fresh output directories and clean release sources. Existing
artifact audit/inventory/installer snapshot protections remain enforced.

Staging DNS is still pending. Building does not resolve the hostname. Runtime use
needs that approved HTTPS origin to work. For an interim Pages origin, provide a
separately reviewed staging `--config` JSON and rebuild; do not use an environment
override, HTTP exception or automatic hostname fallback to evade the compiled pin.

## Secret checks and validation limits

Build subprocesses strip server/operator/provider/signing credentials, including
unneeded website peppers, and staging/production compiler children disable TEST
switches. Customer payload audits reject private server directory names, credential
binding markers and existing private-material formats. Real builds additionally
scan for inherited high-entropy (16+ character) known credential values without
returning/logging them. Unknown arbitrary encrypted bytes cannot be proved secret-free;
public-only profile schema and reviewed build inputs remain essential.

Tests cover public profile isolation, source/local independence, simulated packaged
resource loading/tampering, conflicting environment overrides, disabled packaged
updates, installer inventory inclusion and separate identities, secret names/values,
CLI plan validation and existing desktop/updater/package regressions. They use only
known public synthetic trust fixtures, not production keys. Native Nuitka compilation,
Authenticode/installer signing, real install/portable launch and live licence acceptance
are NOT certified by a dry run. No production build/deployment or secret provisioning
is performed in this task. Approved production public values, DNS, signing/distribution
approval, native build/installer verification and eventual environment-bound updater
configuration remain release gates.


## Existing CI callers

Validation now explicitly plans the committed staging profile. The tag-triggered
Windows release job explicitly selects production; it will fail closed until the
production public template is approved/populated. It never falls back to staging.
Existing release-assembly signing remains a separate job; no signing secret is
introduced into Windows compilation. No workflow was executed or release published
by these source changes.
