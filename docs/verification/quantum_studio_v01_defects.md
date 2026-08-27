# Quantum Studio v0.1 QA defect log

Severity policy: **BLOCKER** prevents launch, core calculation, or risks data corruption. **CRITICAL** can silently produce scientifically wrong output. **MAJOR** breaks an important workflow with a possible workaround. **MINOR** is non-core usability. **COSMETIC** is appearance-only. Statuses are `OPEN`, `NEEDS_RETEST`, `FIXED`, `VERIFIED`, or `DEFERRED`.

| ID | Workspace | Severity | Summary / reproduction | Expected | Actual evidence | Status | Fix commit | Verification |
|---|---|---|---|---|---|---|---|---|
| DEF-START-001 | Calculate | BLOCKER | Startup workspace construction | ProjectWindow initializes Calculate | `_workflow_generated` accessed before initialization | FIXED (automated) | uncommitted hotfix | Calculate workspace regression |
| DEF-CAL-001 | Calculate | MAJOR | Historic manual finding: Configure Bands → Choose Band Path | Structured BandPathDialog opens and accepted path persists | Prior C9R.3 report recorded `bool` / `_band_path` signal failure; current automated evidence exists but no post-freeze human retest | NEEDS_RETEST | — | CAL-002 |
| DEF-CAL-002 | Calculate | MAJOR | Create → Configure → Compile → Generate → Run | Sequential visible lifecycle with current plan/workflow | Historic manual report found Generate/Run not coherent; no QA0 manual evidence | NEEDS_RETEST | — | CAL-001, CAL-005 |
| DEF-CAL-003 | Calculate | MAJOR | Calculate at laptop/fullscreen sizes | Right column/footer actions remain reachable | Historic clipping/action-row report; offscreen coverage exists, manual full-app retest pending | NEEDS_RETEST | — | CAL-009 |
| DEF-CAL-004 | Calculate | MAJOR | Stored cores > available logical CPUs | Value/max clamp to actual availability | Historic `4 > 1` inconsistency; QA0 has no runtime manual check | NEEDS_RETEST | — | CAL-005 |
| DEF-QA-001 | Release | MINOR | Real QE 7.5/MPI/reference validation | Core scientific gate evidence | Not run by QA0 design | OPEN | — | SCI-001–SCI-010 |

QA0 does not resolve these entries. Reproduce and classify in the named QA phase before changing status.

| DEF-CAL-005 | Calculate | MAJOR | Real automatic pseudopotential provisioning | Auto PBE/SSSP Generate or Run | Real SSSP Efficiency 1.3.0 Si selected, SHA verified, and QE reached readpp; materialization is tracked separately | VERIFIED (real evidence) | uncommitted hotfix | real SSSP Si / QE 7.6 run |
| DEF-CAL-006 | Calculate | MAJOR | QE generated inputs visibility | Generate then View QE Inputs | Fixed in hotfix; manual verification pending | FIXED (automated) | uncommitted hotfix | CAL-002 |
| DEF-CAL-007 | Calculate | BLOCKER | Run with no valid QE configuration | Run must discover a validated local QE installation and resume preflight | QE 7.6 was automatically found and launched through MPI in the recorded real run | VERIFIED (real evidence) | uncommitted hotfix | real QE 7.6 launch |
| DEF-CAL-008 | Calculate | BLOCKER | Generated workflow lacks selected pseudopotentials | Generate/Run materializes every selected UPF under workflow `pseudos/` and validates it before pw.x | Real failed Si workflow repaired; local SHA verified; QE 7.6 readpp passed and SCF completed | VERIFIED (real evidence) | uncommitted hotfix | `test_b5_workflow_pseudos` / real Si SCF |
