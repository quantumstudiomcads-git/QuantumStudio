# B4 Release Candidate Audit

- Product: Quantum Studio 0.2.0 beta-rc1
- Commit: `1b9ab4c626c0c74e77dd2bd3f84ea10974c0aaad` (`DIRTY_BUILD`)
- Application package: `<repository-root>/dist/rc/QuantumStudio-0.2.0-beta-rc1-linux-x86_64/QuantumStudio.dist`
- Directory fingerprint: `e4ebcec2d896744a59d6be5f2b0768d4d87eb250bf74dd4f5e59c4be7ea16c0f`
- Package size: 468,172,929 bytes (446.5 MiB); 436 files

## Automated evidence

- Standalone build: PASS
- Packaged no-engine Project Hub/Builder/Calculate/Analyze smoke: PASS
- Packaged `.qs` save/load smoke, spaces and Unicode path: PASS
- Real minimal packaged SCF: PASS; `pw.x` return code 0; parser produced `GroundStateResult` with ResultStore status `VALID`.
- Real smoke execution ID: `494fb6ae5c8f449da906004eaf77cc5e`.
- Engine Pack manifest/hash/platform validation: PASS.
- No optical/phonon/EPW/transport convergence work was launched.

## Truthful gates

- Public catalogue: 147; Extinction Coefficient is a derived Optical Properties observable.
- Scientific statuses remain unconverged/unvalidated as documented.
- Human GUI checklist: PENDING_HUMAN.
- Legal distribution review: LEGAL_TEXT_PENDING_REVIEW.
- This RC was built from a dirty worktree and must not be published as-is.
- Candidate Engine Pack is staged separately; its binary runtime dependency closure requires packaging review before distribution.

## Engine activity

- `pw.x` scientific executions during B4: 3 total — one initial integration smoke plus two bounded diagnostics needed to verify parser/path handling and the staged candidate pack.
- `ph.x`, `epsilon.x`, `epw.x`, `wannier90.x`, `btp2`, `bader`: 0 scientific executions.
- Safe version/help probes are separate from scientific execution.

## Artifacts

- `B4_release_candidate_manifest.json`
- `B4_manual_gui_validation.md`
- `SHA256SUMS`
- `application-files.sha256`

- Source regression rerun: PASS — 435 passed, 0 failed, 0 skipped, 0 xfail; 320 ASE/NumPy dependency warnings. The 404 collection was corrected by `pytest.ini`.

## Pre-commit reconciliation addendum

- Initial 404 collection was caused by pytest default recursion exclusion of `tests/builder/build/`; the 35 legitimate tests in that directory were omitted.
- `pytest.ini` now defines the intended recursion. Canonical regression: **435 collected, 435 passed, 0 failed, 0 skipped, 0 xfail**.
- Test environment: Python 3.13.0, pytest 9.1.1, pytest-qt 4.5.0.
- 320 ASE/NumPy dependency warnings are LOW and non-failing.
- Full classification and proposed commit grouping: `B4_precommit_reconciliation.json`.
