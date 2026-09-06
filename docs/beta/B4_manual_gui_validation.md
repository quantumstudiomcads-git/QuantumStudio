# B4 Manual GUI Validation — Quantum Studio 0.2.0 Beta RC1

Automated checks do not self-certify visual/manual behavior. Complete this checklist on the RC package. Each item is intentionally `PENDING_HUMAN`.

## B4-01 — Project Hub

- **Action:** Open/create/reopen projects; Recent Projects; read-only, spaces and Unicode paths.
- **Expected:** Project opens, no silent engine launch.
- **Result:** `PENDING_HUMAN`
- **Notes:**

## B4-02 — Builder

- **Action:** Create/import, rotate/zoom/pan, select, measure, reciprocal views, Build operations, save/reopen.
- **Expected:** Controls and rendering usable; structure persists.
- **Result:** `PENDING_HUMAN`
- **Notes:**

## B4-03 — Calculate

- **Action:** 147 entries; search; Add/Configure; presets; Generate/View Inputs; Run; failure/retry/reparse affordances.
- **Expected:** Truthful gating and statuses.
- **Result:** `PENDING_HUMAN`
- **Notes:**

## B4-04 — Analyze

- **Action:** Electronic, phonon, transport and optical fixtures; selectors; PNG/PDF/SVG/numeric export.
- **Expected:** Plots and exports are usable; no engine launch.
- **Result:** `PENDING_HUMAN`
- **Notes:**

## B4-05 — Engine Pack

- **Action:** No pack, valid pack, invalid/relocated pack, diagnostics.
- **Expected:** Availability updates without crash.
- **Result:** `PENDING_HUMAN`
- **Notes:**

## B4-06 — Persistence

- **Action:** Save/load `.qs`, ResultStore visibility, close/reopen.
- **Expected:** No corruption or rerun.
- **Result:** `PENDING_HUMAN`
- **Notes:**

## B4-07 — Failure/recovery

- **Action:** Fake missing engine, failure, cancel, interrupt, reparse, disk warning.
- **Expected:** Correct action/status.
- **Result:** `PENDING_HUMAN`
- **Notes:**

## B4-08 — About/Diagnostics

- **Action:** Version 0.2.0, Beta RC1, commit, paths, logs and redaction.
- **Expected:** No secrets/developer paths.
- **Result:** `PENDING_HUMAN`
- **Notes:**

## B4-09 — Packaging

- **Action:** Launch installed copy from spaces path/read-only root; theme/icons; fit primary windows.
- **Expected:** Source-independent startup.
- **Result:** `PENDING_HUMAN`
- **Notes:**

## Publication gate

- Human GUI validation: `PENDING_HUMAN`
- Legal distribution review: `LEGAL_TEXT_PENDING_REVIEW`
- Do not create a tag or publish until both are resolved.
