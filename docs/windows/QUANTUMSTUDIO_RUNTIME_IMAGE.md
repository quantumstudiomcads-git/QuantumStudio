# QuantumStudioRuntime image contract

W3 defines an offline-first artifact contract for the private WSL appliance. It does not create or commit a production root filesystem.

## Identity and source

The distro identity is exactly `QuantumStudioRuntime`; it is never versioned in the distro name. `ManagedRuntimeImage` describes one local rootfs with:

- `runtime_id`: exactly `QuantumStudioRuntime`;
- independent runtime version in `major.minor-runtime.revision` form (for example `0.2-runtime.1`);
- Windows platform and CPU architecture;
- a local source path and exact SHA-256 digest;
- `WSL_ROOTFS_TAR` format, presently a `wsl.exe --import`-compatible tar;
- optional build ID, timestamp, host requirement, and metadata-schema descriptor.

The installer may carry this rootfs beside or inside its package. W3 makes no network request and does not infer trust from a filename. The complete rootfs is hashed before an import plan can be executed. Missing, non-file, malformed-digest, platform/architecture mismatch, and digest mismatch are typed blocking failures.

## In-runtime metadata

The imported image must provide `/opt/quantumstudio/runtime/runtime.json`, a JSON object with:

```json
{
  "runtime_id": "QuantumStudioRuntime",
  "runtime_version": "0.2-runtime.1",
  "schema_version": "1",
  "architecture": "x86_64",
  "build_id": "reproducible-build-id",
  "build_timestamp": "2026-09-08T00:00:00Z",
  "image_sha256": "<64 lowercase-or-uppercase hex characters>"
}
```

W3 reads this file only by the fixed structured argv `wsl.exe --distribution QuantumStudioRuntime --exec cat /opt/quantumstudio/runtime/runtime.json`. It accepts no arbitrary distro, command, or in-distro path. Identity, schema, parseable version, architecture, and image digest are validated after import.

## Future filesystem model

Replaceable runtime/system components belong under `/opt/quantumstudio/`:

- `runtime/runtime.json`
- `engines/` (future Engine Pack only)
- `manifests/`
- `licenses/`

Mutable scientific data must remain conceptually separate under `/var/lib/quantumstudio/`, including future `workflows/`, `pseudopotentials/`, `reusable-states/`, and `staging/`. W3 does not implement this data store, but upgrades must not assume that replacing a base runtime justifies destroying it.

The initial import may use root as an appliance bootstrap account. W3 neither requires an interactive Linux user nor creates passwords, sudo prompts, or a first-run Ubuntu desktop flow. A later execution hardening pass may introduce a dedicated runtime user.

## Runtime-agent installation contract

The future reproducible rootfs build must install the first-party, standard-library-only `runtime_agent` source as an executable entry point at `/opt/quantumstudio/runtime/bin/qs-runtime-agent`. The host invokes only this fixed endpoint with `health` or `run`; no agent is downloaded or installed dynamically. Runtime metadata may later record the compatible agent version.

## Image production

A reproducible production rootfs build pipeline is intentionally deferred: it may require external container, debootstrap, licensing, or Windows validation tooling. Tests use only tiny local mock files. No QE, EPW, Wannier90, BoltzTraP2, or other scientific engine is included by this contract.
