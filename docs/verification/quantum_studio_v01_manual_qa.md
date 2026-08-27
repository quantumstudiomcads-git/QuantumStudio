# Quantum Studio v0.1 manual QA plan

Record Actual result, PASS/FAIL, and defect ID for every case. Use the project-local fixtures and never execute a real scientific binary until QA6.

| ID | Precondition | Steps | Expected behavior | Actual / status / defect |
|---|---|---|---|---|
| BLD-001 | Empty project | Open Builder | Empty structure state is concise and stable | ____ |
| BLD-002 | Valid Si/CIF fixture | Import, render, rotate, zoom, reset/view x*/y*/z*, change background | Correct structure/camera; no clipping | ____ |
| BLD-003 | Rendered structure | Create/clear measurement | Correct value and clear behavior | ____ |
| BLD-004 | Small crystal | Supercell and slab; undo/redo | Derived structure correct; history restores source | ____ |
| BLD-005 | Suitable fixture | Build nanotube, heterostructure, moiré | Validation/lattice-match messages are actionable | ____ |
| BLD-006 | Recognized lattice | Open BZ and request band path | Public BZ/path recommendation is structured | ____ |
| BLD-007 | Modified Builder project | Save, close, reopen; maximize/restore; try invalid import | State restores; errors remain non-destructive | ____ |
| DEV-001 | Builder structure | Send/open in Device Builder; add two regions | Source remains isolated; selection clear | ____ |
| DEV-002 | Device fixture | Translate, rotate, repeat and fit cell | Geometry updates as requested | ____ |
| DEV-003 | Overlap fixture | Force collision/invalid placement | Clear rejection; model remains valid | ____ |
| DEV-004 | Compatible layers | Interface match, heterostructure, moiré | Explicit convention/result and failures | ____ |
| DEV-005 | Device project | Apply template, undo/history, save/reopen, resize | Persistence/history/responsive layout work | ____ |
| CAL-001 | Si project | Select SCF → Create → Configure PBE → Compile → Generate | Persistent request, sequential state/button enablement | ____ |
| CAL-002 | Bands fixture | Create Bands → Configure PBE + path → Compile → Generate | Band-path dialog opens/accepts/persists; plan is current | ____ |
| CAL-003 | Bands fixture | Configure HSE06, compatible pseudo, EXX mesh and path | Clear validation; hybrid plan/generation only | ____ |
| CAL-004 | Any request | Configure SOC, auto pseudo, then manual pseudo | Compatibility/status visible; no silent replacement | ____ |
| CAL-005 | Fake local tools | Set 1/2/4 cores/MPI/OpenMP → Run → Cancel | CPU bound valid; structured launch; cancel safe | ____ |
| CAL-006 | Missing pw.x/MPI/pseudo fixtures | Attempt Run/Generate | Precise preflight/generation error; no process starts | ____ |
| CAL-007 | Interrupted fake workflow | Retry/recovery and save/reopen | Attempts/artifacts preserved; stale run handled safely | ____ |
| CAL-008 | Parsed fixture results | Results browser → Parse/Re-parse; save/reopen | Correct execution isolation/root registration | ____ |
| CAL-009 | 1280×720/1366×768/1920×1080 | Open Calculate, maximize/restore | Buttons/plan/footer visible; no clipping | ____ |
| ANL-001 | Empty project | Open Analyze | “No results to analyze” only; no raw-folder requirement | ____ |
| ANL-002 | Calculation without parsed Result | Open Analyze | Parse-in-Calculate guidance, not execution failure | ____ |
| ANL-003 | SCF/Bands/DOS/PDOS/phonon fixtures | Switch Result repeatedly | Plot/navigation/provenance/filter state follows Result | ____ |
| ANL-004 | Bands result | Mark edges; select Absolute/Fermi/VBM references | Conservatively worded values and non-mutating display | ____ |
| ANL-005 | Analytic/parabolic Bands fixture | Carrier → edge → direction → points → Fit → change input → Fit Preview | Prior fit clears; diagnostics/Δk units/poor-fit text visible | ____ |
| ANL-006 | Compatible two/three series | Add/reorder/hide/rename; overlay/difference | Explicit B-A direction and eligibility reason | ____ |
| ANL-007 | PDOS fixture | Filter/aggregate then select no matching channel | Table/plot match filters; explanatory empty state | ____ |
| ANL-008 | Explicit strain fixture | Open derived trend/export | Numeric sort, sampled-path naming, provenance CSV | ____ |
| ANL-009 | Stale/partial/corrupt/missing-root fixtures | Select alongside valid Result; Refresh | Warning remains textual; other Results remain usable | ____ |
| ANL-010 | Any plot/comparison | CSV/image/comparison/JSON exports; resize/fullscreen | Correct extensions, no UI chrome, dark dialogs/tooltips | ____ |
| INT-001 | Builder structure | Builder → Calculate request → change Builder | Request keeps historical snapshot | ____ |
| INT-002 | Builder structure | Builder → Device; edit Device | Builder source stays unchanged | ____ |
| INT-003 | Fake Calculate execution | ResultStore → Analyze; switch execution | Result identity/provenance remain execution-specific | ____ |
| INT-004 | Multi-workspace project | Save → close → reopen all workspaces | Structure/device/requests/roots/Results restore | ____ |
| REL-001 | Fresh environment | Create first project; missing QE/MPI; offline cache; launcher | Startup and optional-tool guidance work | ____ |

The Analyze-specific detailed checklist remains at `docs/verification/analyze_v01_checklist.md`; ANL-001 through ANL-010 incorporate it rather than replacing it.
