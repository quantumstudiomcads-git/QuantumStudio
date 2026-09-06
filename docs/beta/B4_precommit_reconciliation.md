# B4 Pre-Commit Reconciliation

Repository: `<repository-root>`
Branch: `v0.2`
HEAD: `1b9ab4c626c0c74e77dd2bd3f84ea10974c0aaad`

## Test reconciliation

- Before configuration: 404 collected/passed.
- Root cause: pytest’s default `norecursedirs` excludes any directory named `build`.
- Omitted legitimate tests: 35 in `tests/builder/build/`.
- Added `pytest.ini` with explicit `testpaths=tests` and controlled recursion.
- Canonical result: **435 collected, 435 passed, 0 failed, 0 skipped, 0 xfail**.
- Historical B3 value 435 was accurate for the intended suite; 404 was a collection defect.

## Environment

- Python 3.13.0; pytest 9.1.1; pytest-qt 4.5.0; PySide6 6.11.2; ASE 3.28.0; NumPy 2.5.2; SciPy 1.18.1; Matplotlib 3.11.1.
- `requirements-runtime.txt` and `requirements-test.txt` are pinned to the verified environment.
- `pip install --no-index --no-deps -r requirements-test.txt` reports all requirements satisfied in `.venv-test`.

## Warnings

- 320 ASE/NumPy DeprecationWarnings from `ase/atoms.py` ndarray shape assignment; dependency warning, LOW, no observed breakage.

## Runtime artifacts

- Current tests do not write `backend/artifacts/`; existing UUID directories are preserved historical/manual runtime artifacts and ignored.
- `backend/test_manifest.py` is a legacy manual script with an explicit source-tree output path; it is not part of pytest collection or production startup.
- Deployment output and scientific scratch are ignored; nothing was deleted.

## Worktree

- Classified paths: 151 (DOC_B1_B4=16, PACKAGING_SOURCE=4, SOURCE_B1_B4=104, TEST_B1_B4=27).
- No files are staged.
- No tracked files exceed 10 MiB.
- Worktree remains dirty because it contains the full uncommitted B1–B4 and earlier calculation implementation set plus preserved runtime artifacts.

## Proposed commit plan

1. Review/stage the pre-beta calculation/workflow implementation as a coherent source unit.
2. Review/stage optical architecture and its tests/provenance separately if diffs are sufficiently independent.
3. Stage B1–B4 hardening, pytest configuration, dependency manifests, packaging source and beta docs.

Explicitly exclude generated deployment trees, RC packages, Engine Pack binaries, backend/artifacts, scientific scratch, virtual environments, and user validation data. No commit was made and no RC rebuild was performed.
