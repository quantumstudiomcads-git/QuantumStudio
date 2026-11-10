# Staging and production updater contract

## Audit and scope

The existing updater verifies Ed25519 signatures over canonical JSON for both the
B6 manifest and each artifact record, then validates downloaded size and SHA-256.
The `kid` is signed. Beta/stable release channels, semantic version ordering and
Engine Pack compatibility/version checks already existed. HTTPS transport rejects
redirects. A per-user update history was advisory, not an anti-replay authority.
There was no signed deployment environment, manifest expiry or persistent revision
floor. A legacy client configured with a shared key and beta channel could not
cryptographically distinguish staging from production metadata. Packaged clients
were disabled, so that gap was not exposed by the shipped packaged configuration.

This change defines a separate v2 deployed protocol. Existing source B6/schema-1
updater behavior stays available for development; it cannot consume v2 by silently
setting an environment/feed variable. Packaged local profiles have no deployed
update channel. Licensing/signing-service behavior and licence schema are unchanged.
No update, deployment, real signing key or external channel was provisioned.

## Explicit profiles and safe disable

The executable-pinned Windows desktop public JSON may contain an `updates` member:

```json
{
  "schema_version": 1,
  "enabled": false,
  "environment": "staging",
  "channel": "beta",
  "manifest_endpoint": "https://staging.quantumstudiomcads.com/updates/staging/release-manifest.json",
  "trust": {
    "schema_version": 1,
    "environment": "staging",
    "domain": "update",
    "algorithm": "Ed25519",
    "keys": {}
  }
}
```

The corresponding production endpoint is
`https://quantumstudiomcads.com/updates/production/release-manifest.json`, with
`environment:production`, channel `beta` for this closed beta, and independent
production update trust. Environment and release channel are distinct: the bound
identity is `(staging,beta)` or `(production,beta)`, never an inferred default.
Only explicit beta/stable release channels are supported; local/dev are rejected.

Both tracked profiles remain **enabled=false with empty update key rings**. Missing
update settings or disabled/incomplete trust never fall back to process feed/key
variables or shared beta/stable preferences. Malformed/tampered packaged resources
retain the existing fail-closed profile behavior; the application is not forced to
exit. The source/development updater remains a distinct legacy path.

For enablement, populate approved PUBLIC update keys, use `enabled:true`, align the
HTTPS endpoint origin with that profile's approved website origin, and rebuild the
executable-bound pin. Changing an environment variable or editing the installed
JSON cannot enable/redirect it. Disabled configuration can retain the intended
future HTTPS endpoint while interim staging uses a reviewed Pages origin. There
is no live-DNS lookup during build/test and no automatic hostname/HTTP fallback.

The selected build channel must equal the enabled update channel. Build/installer
metadata records enabled versus disabled and verifies the same selected JSON/hash.
Only the selected environment's public update settings are included. Other
profiles' trust and private keys are not bundled. Old profiles without `updates`
remain safely update-disabled.

## Independent signature and trust model

Use independent persistent update signing identities for staging and production,
AND separate them from licence-signing identities. Do not use the licence Worker
or its private key to sign updates. Public key IDs must be:

- staging: `upd-staging-` followed by 1-64 lowercase identifier characters;
- production: `upd-production-` followed by 1-64 lowercase identifier characters.

The existing raw 32-byte public key encoding is canonical unpadded base64url.
Trust JSON is environment-tagged with domain `update` and algorithm `Ed25519`.
Enabled trust has 1-32 approved keys. Signatures are canonical unpadded base64url
of exactly 64 Ed25519 signature bytes; alternate textual encodings cannot create
different receipt digests for the same signed body. Package validation rejects key bytes reused
from that same profile's licence trust. Operators must independently provision
and approve different staging/production update key material; raw Ed25519 bytes
carry no intrinsic provenance, and a package does not contain the other environment's
key ring for comparison. Namespace/environment checks alone do not make reuse of a
compromised shared private key safe.

Each package verifies using ONLY its pinned update keys, never a key supplied by a
manifest or process variable. Both top-level and artifact signatures cover every
received field except `signature`, including kid, purpose, environment and channel.
Canonical bytes remain sorted compact UTF-8 JSON with ensure_ascii=False and
allow_nan=False. New contract metadata cannot be consumed as legacy schema 1.
Private update keys stay in separately approved release-publishing infrastructure;
they never enter Pages, the licence Worker, desktop resources or public manifests.

Rotation requires an approved rebuild distributing old+new public pins before using
a new signing identity, then a new increasing revision. Retain old verification keys
as needed for supported packages and immutable artifacts. Do not rotate by relabeling
staging/TEST keys or resetting client receipt state.

## Signed v2 manifest and artifact fields

The top-level object has exactly:

```text
schema_version = 2
purpose = quantum-studio:update-manifest:v2
environment = staging | production
channel = beta | stable
revision = integer, 1 .. 2^63-1
version = existing semantic application version
published_at = timezone-aware ISO-8601 timestamp
expires_at = explicit future UTC Unix timestamp (integer, through year 9999)
minimum_supported_version, mandatory, release_notes_url, release_notes_summary
platforms, engine_pack
kid, signature
```

No environment/channel/purpose/expiry/revision omission or schema-1 fallback is
accepted by deployed clients. Future publication times beyond 300 seconds of skew,
expired manifests, expiry before publication, invalid signatures, invalid shapes
and foreign environments/channels are rejected. HTTPS JSON responses are bounded
to 1 MiB and reject duplicate/non-finite fields.

Each signed platform/Engine Pack record carries:

```text
schema_version = 2
purpose = quantum-studio:update-artifact:v2
environment, channel
release_version = exact top-level version
release_revision = exact top-level revision
filename, url, size, sha256, artifact_type, platform, architecture
kid, signature
```

Existing optional application-version bounds remain supported. Engine Pack records
also retain component version and minimum/maximum runtime schema. Filenames use
bounded safe ASCII syntax and reject Windows reserved names. Artifacts and release
notes must be on the approved HTTPS origin under `/updates/<environment>/artifacts/`,
without credentials, query, fragment, redirects or encoded path escapes. Supported
artifact types/platform pairs remain Windows installer, Linux AppImage and Linux
Engine Pack. Signed parent and artifact release bindings prevent detached metadata
from being reused in another environment/channel/revision/version.

Signatures authenticate metadata approval; publishing must still audit that input
binaries/installer profiles are the intended environment. They cannot protect
against an authorized malicious signer deliberately approving arbitrary bytes.

## Version, replay and download protection

Existing semantic version ordering and legacy Engine Pack compatibility/version
checks remain intact. Deployed clients reject versions older than the installed
application. A cross-process SQLite receipt at the selected user config root stores
`(environment/channel, highest revision, manifest digest, highest accepted version,
checked-at time)` using BEGIN IMMEDIATE and atomic commit.

It rejects lower revisions, a different signed body at the same revision, semantic
version rollback even at a higher revision, and backward clock movement. Corrupt,
unreadable, locked or unwritable receipt state fails closed; it is not optional
advisory history. The existing human-readable update history remains separate.
An identical manifest retry before expiry is intentionally idempotent, so failed
network/download attempts can be retried. Once a newer receipt is accepted, an old
checked result cannot be staged. Receipt/expiry/signature checks run again before
AND after download, so a concurrent newer check prevents a stale ready result.

Deployed staging directories include environment/channel/revision/manifest digest;
older candidates cannot overwrite a newer revision's staged file. Existing size and
SHA-256 checks must pass before bytes become ready. Mismatches remove partial data
and never provide an installable result. No artifact is executed by these checks.

Receipt guarantees depend on retaining that local state and a trustworthy clock.
A fresh install or deliberately deleted/rolled-back user state cannot know a revision
it has never seen; installed semantic version, signature, expiry and pinned HTTPS
source still apply. This is not hardware-backed anti-rollback or protection against
an attacker who can replace the executable or mutate privileged local state.

Rollback policy is roll-forward: publish corrected bytes under a HIGHER application
version and a NEW revision. Do not reset floors, reuse a revision for a different
body, silently downgrade or add an unsigned emergency exception. An unchanged
artifact retry uses the original signed files; regenerating a manifest changes its
body and requires a new revision.

## Publishing workflow (not executed here)

The existing offline `scripts/build_release.py` now accepts:

```powershell
python scripts/build_release.py --version <approved-version> --channel beta --update-profile <reviewed-desktop-public-json> --revision <new-increasing-integer> --expires-at <future-UTC-Unix-seconds> --windows-artifact <audited-matching-installer.exe> --linux-artifact <audited-matching.AppImage> --output <fresh-release-directory>
```

The existing tool still requires both platform inputs. Windows public-profile
packaging is integrated here; Linux native profile enablement is not implemented
or certified by this step. The publisher does not retrofit a profile into a binary:
independently audit each matching-environment platform input before promotion. It derives artifact URLs
from the selected public origin/environment. A supplied base URL must remain in
the approved artifact namespace. Deployed filenames include version and revision;
keep those public URLs immutable. External `QUANTUM_STUDIO_UPDATE_SIGNING_KEY` and
`QUANTUM_STUDIO_UPDATE_SIGNING_KID` are publisher secrets only. The tool derives the
public key and requires it to match the approved update pin before signing. It
verifies the completed manifest through the consumer's v2 parser before writing
its authoritative pointer. No ephemeral/dry-run signer fallback is allowed when a
deployed profile is selected. Legacy development dry-run behavior is unchanged.

1. Independently approve separate public update pins and secure private custody.
2. Audit matching-environment packages/installer metadata and keep inputs immutable.
3. Choose a strictly increasing revision and appropriate explicit expiry.
4. Assemble into a fresh local output directory using the matching approved signer.
5. Verify all signed metadata/digests; upload immutable artifacts first and confirm
   availability at the declared environment URLs.
6. Promote the exact signed manifest LAST at the profile's endpoint, atomically.
   The transport appends `?channel=beta` or stable; hosting must serve the matching
   reviewed channel record. There is one explicitly selected channel per package.
7. Test controlled same-channel update, wrong-environment rejection, corruption,
   expiry, replay and rollback before broader rollout. Keep originals for retries.

The existing tag workflow now explicitly passes the production public profile and
requires public repository variables `PRODUCTION_UPDATE_REVISION` and
`PRODUCTION_UPDATE_EXPIRES_AT`. Existing signing secrets remain only in the separate
release-assembly job. It will fail until the production profile is complete/enabled
and the signer matches. GitHub draft assets are not deployment to the approved
update origin: final website/artifact promotion remains a separately authorized
manual operation. No workflow, deployment or publishing action was run here.

## Exact gates before enablement

- Approve production licence public configuration independently (its template is
  still incomplete) and approve BOTH environment-specific update public key rings.
- Establish secure dedicated update private-key custody; generate/provision no keys
  through the desktop or public website. No real update keys were generated here.
- Make the approved HTTPS origins/endpoints operational, with immutable artifact
  hosting, appropriate caching and atomic final-manifest promotion. DNS remains pending.
- Review complete public profiles, set enabled=true only after approval, and rebuild
  the executable pin/installer. Existing installed JSON/env edits are not enablement. The first enabled package
  must be installed through a separately approved manual installer update; an old
  disabled package cannot remotely enable itself.
- Validate native package/installer behavior, publisher tooling and the public serving
  path with a controlled staging pilot; independently approve production rollout.

Tests use known synthetic seeds, mocked/local transports and temporary output only.
They cover both environments, signatures, content digest, revision/clock/version
rollback, equivocation, race checks, safe disable, publisher and package integration.
A Windows plan-only build does not certify native compilation, real install/update
or live hosting. Those remain manual release gates. Licensing's mandatory online
validation and no-offline-grace policy are unchanged.
