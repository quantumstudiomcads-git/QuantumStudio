# Quantum Studio v0.2 — B1 Beta Hardening Audit

## Baseline and scope

The accepted W8.4 baseline was `windows-beta-v0.2` at `eec18a1f0fa29b64a54fdee6a62b4350b655824f` (`Restore Quantum Studio v0.2 application parity`). It is frozen as annotated tag `v0.2.0-beta-w8.4`. Hardening work is on `beta-hardening-v0.2`.

B1 covered application recovery, project persistence, recent-project state, paths, Builder/Calculate/Analyze failure boundaries, optional runtime/engine/pseudo availability, execution/cancellation/recovery, results/provenance, diagnostics, Windows behavior, offline assumptions, and security boundaries. No scientific feature or `.qs` schema semantics were changed.

## Test matrix and findings

| Area | Tested | Findings | Highest severity |
|---|---|---|---|
| Startup/shutdown | Existing source/offscreen/runtime coverage; static review | Optional runtime discovery is isolated from basic GUI construction; full native click-through not available in this run | P2 |
| Projects/save/open/save-as | Atomic save and legacy persistence tests plus new corrupt fixtures | Malformed top-level data previously produced raw type errors; fixed | P1 |
| Corrupt `.qs` | Empty, truncated/invalid JSON, future version, wrong structure type, bad atom data | Safe refusal with `ProjectLoadError`; original preserved | P1 |
| Recent projects | Missing, duplicate, malformed entries, Unicode/spaces paths | Invalid entries ignored; atomic state write and cleanup | P1 |
| Paths | Unicode/spaces, Windows runtime namespace, missing parents | Native Windows runtime-path mapping fixed; exotic unsupported paths fail clearly | P0 |
| Builder/import | Structure I/O and Builder regression coverage | Parser errors are surfaced at boundaries; no renderer/science change | P1 |
| Calculate/runtime absence | Registry, discovery, preflight, pseudo and managed-runtime tests | Configuration/catalog browsing remains separable from execution | P1 |
| Pseudos | Missing/corrupt/hash/metadata/incomplete-set tests | Fail closed; no silent substitution | P0 |
| Execution/cancellation | Local/managed fake executables, nonzero exits, cancellation, stale recovery | Structured argv and `shell=False`; stale runs become INTERRUPTED | P0 |
| Results/Analyze | ResultStore, parser, stale/provenance and broken-result tests | Status and provenance remain distinct; broken result is isolated | P1 |
| Logging/error reporting | Static inventory and existing diagnostic extraction | QE failure extraction exists; broad application log export remains follow-up | P2 |
| Diagnostics | New metadata collector/export tests | Metadata-only deterministic ZIP foundation added; Help UI deferred | P1 |
| Windows/offline | Native Windows suite, path/runtime tests, resource/path review | GUI startup has no mandatory scientific runtime/network dependency | P1 |
| Security | Targeted search and archive/path containment review | No new shell construction; existing intentional subprocesses are structured | P0 |

## Fixed findings

### BH-P0-001 — Native Windows runtime-path execution rejected or staged to the wrong drive

Reproduction: run the existing W4/W5 runtime-agent tests on native Windows with temporary directories on a non-system drive. POSIX wire paths were passed through `pathlib.Path` as if they were host paths, producing `CWD_REJECTED`, incorrect staging roots, or failure to launch the trusted fixture.

Risk: normal managed-execution preparation/cancellation tests could fail, and path handling could target the wrong host location.

Fix: `runtime_agent/agent.py` now uses a drive-aware host adapter only for native source-mode execution, maps namespaced paths in argv, and requires the script argument to remain under a trusted executable root. Managed Linux wire semantics and structured `shell=False` execution remain unchanged.

Regression: `tests/calculate/test_w4_execution_bridge.py`, `tests/calculate/test_w5_managed_scientific_runtime.py` — 17 passed, 7 subtests.

### BH-P1-001 — Malformed project payloads surfaced as raw type/attribute errors

Reproduction: load an empty file, non-object JSON, future schema, wrong structure type, or an atom with invalid coordinates.

Risk: unclear UX and possible workspace crash before a recoverable refusal.

Fix: `frontend/core/project.py` validates the top-level container, supported schema version, project metadata, and structure payload; it raises actionable `ProjectLoadError`. Save-as now commits `file_path` only after a successful atomic replace, preserving the current project identity after failure.

Regression: `tests/runtime/test_b1_beta_hardening.py` and legacy persistence tests.

### BH-P1-002 — Malformed recent-project entries could abort state update

Reproduction: call recent-project persistence with non-path entries or a write failure.

Fix: invalid entries are ignored, state writes use a temporary file and replace, and temporary remnants are cleaned up.

### BH-P1-003 — No privacy-safe diagnostics export backend

Fix: `backend/runtime/diagnostics_service.py` provides safe metadata collection and a deterministic metadata-only ZIP with an explicit `manifest.json`; it never zips project/scientific data. Help UI integration is deferred to B2.

## Deferred backlog and residual risk

P2 items are recorded in `BETA_HARDENING_BACKLOG.md`: full application logging/rotating log policy, user-facing diagnostics UI, and native multi-monitor/DPI manual matrix. No justified remaining P0/P1 defect was found after the fixes.

Residual risk: this source-mode validation does not replace physical packaged r20 click-through verification; no r21 package was built because no frozen-resource behavior changed. Read-only and ACL behavior is covered by failure propagation/atomic-save design, but exact Windows ACL permutations need a dedicated manual matrix.

## Functional hardening summary

Project saves are temp-file + flush + fsync + atomic replace; failed Save As does not change the in-memory target. Corrupt projects are refused without rewrite, while supported `0.2`/`0.3` legacy projects continue to load. Recent state is bounded, deduplicated, and tolerant of missing/malformed entries.

Execution remains structured and shell-free. Missing executables/cwd/input/artifacts are preflight failures; nonzero exits, timeouts, cancellation, stale `RUNNING`, partial results, parse failures, and stale provenance remain distinct states. No automatic rerun or unrelated process termination was introduced.

Diagnostics exports product/build/platform/Python/Qt identity, configured application roots, and explicit not-probed runtime/Engine Pack/WSL states. They exclude project files, coordinates, inputs, scientific outputs, pseudo contents, secrets, and licence material.

## B2/B3/B4/B5 follow-ups

- B2 UI: Help → Export Diagnostics, polished recovery messaging, full DPI/geometry/manual click-through matrix.
- B3 Catalogue: catalogue-gap audit only; no new entries were added in B1.
- B4 Licensing: identify future entitlement boundary at application/runtime provisioning; no licensing code was added.
- B5 Manual: document current surfaces, recovery states, and known beta limitations using this audit as source material.
- W8.5 Installer: packaged hardening candidate only when frozen-specific changes justify a new generation.

## Scientific compatibility statement

QE, EPW, Wannier90, BoltzTraP2, transport, optical, vibrational, pseudopotential selection science, ResultStore scientific interpretation, `.qs` schema semantics, Builder geometry mathematics/renderer, Device Builder physics, and the canonical catalogue of 147 public calculations are unchanged.
