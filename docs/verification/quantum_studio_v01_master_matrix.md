# Quantum Studio v0.1 master verification matrix

This is the authoritative release-verification inventory for v0.1. A `PASS` records evidence, not merely implemented code. `NOT_TESTED` means no required evidence has been collected. Status vocabulary: `NOT_TESTED`, `PASS`, `FAIL`, `BLOCKED`, `NOT_APPLICABLE`. “Scientific validation” always means real reference-output validation, not a fixture test.

## Freeze rule

v0.1 is in whole-application QA. Allowed changes are defect, scientific-correctness, release-blocker, performance, accessibility/usability, and packaging/install fixes. New Builder, Device Builder, Calculate, and Analyze feature scope is prohibited unless v0.1 freeze is explicitly lifted.

## Evidence legend

- **Unit**: Qt-free/component coverage.
- **GUI**: offscreen or human workspace coverage.
- **Integration**: public subsystem boundary/persistence coverage.
- **Scientific**: real executable/reference-result validation.

## Builder inventory (23 audited capabilities, grouped into 11 matrix rows)

| Feature | Workspace | Implemented | Unit | GUI | Integration | Persistence | Scientific | Failure | Performance | Status | Notes / defect |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Project startup and structure handoff | Builder | yes | PASS | NOT_TESTED | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | NOT_TESTED | Cross-workspace QA5 |
| Import/native Structure/ASE boundary | Builder | yes | PASS | NOT_TESTED | PASS | PASS | N/A | PASS | NOT_TESTED | NOT_TESTED | BLD-001 |
| Structure viewing, camera, x*/y*/z*, background | Builder | yes | PASS | PASS | N/A | N/A | N/A | NOT_TESTED | NOT_TESTED | NOT_TESTED | BLD-002 |
| Measurement | Builder | yes | PASS | NOT_TESTED | N/A | NOT_TESTED | N/A | NOT_TESTED | NOT_TESTED | NOT_TESTED | BLD-003 |
| Supercell and slab | Builder | yes | PASS | NOT_TESTED | N/A | PASS | N/A | PASS | NOT_TESTED | NOT_TESTED | BLD-004 |
| Nanotube | Builder | yes | PASS | NOT_TESTED | N/A | NOT_TESTED | N/A | PASS | NOT_TESTED | NOT_TESTED | BLD-005 |
| Heterostructure/lattice matching | Builder | yes | PASS | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | BLD-006 |
| Moiré construction | Builder | yes | PASS | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | BLD-007 |
| Brillouin zone and public band-path API | Builder | yes | PASS | NOT_TESTED | PASS | N/A | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | BLD-008 |
| Undo/redo and structure replacement semantics | Builder | yes | PASS | NOT_TESTED | NOT_TESTED | PASS | N/A | PASS | NOT_TESTED | NOT_TESTED | BLD-009 |
| Save/reopen and responsive/maximized layout | Builder | yes | PASS | NOT_TESTED | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | NOT_TESTED | BLD-010 |

## Device Builder inventory (19 audited capabilities, grouped into 8 matrix rows)

| Feature | Workspace | Implemented | Unit | GUI | Integration | Persistence | Scientific | Failure | Performance | Status | Notes / defect |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Device model, regions, components, selection | Device Builder | yes | PASS | PASS | N/A | PASS | N/A | PASS | NOT_TESTED | NOT_TESTED | DEV-001 |
| Placement/translation/rotation/repetition | Device Builder | yes | PASS | PASS | N/A | PASS | N/A | PASS | NOT_TESTED | NOT_TESTED | DEV-002 |
| Cell fitting/collision detection | Device Builder | yes | PASS | NOT_TESTED | N/A | PASS | N/A | PASS | NOT_TESTED | NOT_TESTED | DEV-003 |
| Interface construction/lattice matching | Device Builder | yes | PASS | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | DEV-004 |
| Heterostructure and moiré integration | Device Builder | yes | PASS | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | DEV-005 |
| Templates | Device Builder | yes | PASS | PASS | N/A | PASS | N/A | PASS | NOT_TESTED | NOT_TESTED | DEV-006 |
| History/undo, source isolation, responsive GUI | Device Builder | yes | PASS | NOT_TESTED | PASS | PASS | N/A | NOT_TESTED | NOT_TESTED | NOT_TESTED | DEV-007 |
| Device → future simulation boundary | Device Builder | architecture | PASS | N/A | NOT_TESTED | PASS | N/A | N/A | N/A | NOT_APPLICABLE | No v0.1 simulation executor |

## Calculate inventory (32 audited capabilities, grouped into 13 matrix rows)

| Feature | Workspace | Implemented | Unit | GUI | Integration | Persistence | Scientific | Failure | Performance | Status | Notes / defect |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Public catalog (147: 20 ready, 1 partial, 126 planned) | Calculate | yes | PASS | NOT_TESTED | PASS | N/A | N/A | PASS | N/A | NOT_TESTED | Catalog count source-verified |
| Request creation/snapshot/persistence | Calculate | yes | PASS | NOT_TESTED | PASS | PASS | N/A | PASS | NOT_TESTED | NOT_TESTED | CAL-001/QA3 |
| Parameter presets, functional registry, SOC | Calculate | yes | PASS | NOT_TESTED | PASS | PASS | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | PZ/PBE/PW91/BLYP/HSE06/B3LYP |
| Pseudo assignment/provisioning/cache/provider checks | Calculate | yes | PASS | NOT_TESTED | PASS | PASS | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | Network/provider validation deferred |
| Band-path selection | Calculate | yes | PASS | NOT_TESTED | PASS | PASS | NOT_TESTED | PASS | N/A | NOT_TESTED | DEF-CAL-001 needs manual retest |
| Compiler/ExecutionPlan/QE generation | Calculate | yes | PASS | NOT_TESTED | PASS | N/A | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | SCI-001 onward |
| Hybrid bands / ADDITIONAL_K_POINTS / bands.x | Calculate | yes | PASS | NOT_TESTED | PASS | N/A | NOT_TESTED | PASS | N/A | NOT_TESTED | SCI-005 high risk |
| Wannier90, EPW, BoltzTraP2 generation | Calculate | yes | PASS | NOT_TESTED | PASS | N/A | NOT_TESTED | PASS | N/A | NOT_TESTED | Runtime validation needed |
| NEGF | Calculate | architecture | PASS | N/A | NOT_TESTED | N/A | NOT_TESTED | N/A | N/A | NOT_APPLICABLE | Architecture-only, not marketable as execution |
| Local tools/CPU/MPI/OpenMP/preflight | Calculate | yes | PASS | NOT_TESTED | PASS | session-only | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | MPI validation SCI-006 |
| Create → Compile → Generate → Run/Cancel/retry/recovery | Calculate | yes | PASS | NOT_TESTED | PASS | execution sidecars | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | DEF-CAL-002 needs manual retest |
| Execution roots/result parsing/reparse/browser | Calculate | yes | PASS | NOT_TESTED | PASS | PASS | NOT_TESTED | PASS | NOT_TESTED | NOT_TESTED | Parser validation SCI-007 |
| Responsive layout/error UX/fullscreen | Calculate | yes | PASS | NOT_TESTED | NOT_TESTED | N/A | N/A | NOT_TESTED | NOT_TESTED | NOT_TESTED | DEF-START-001 fixed by automated regression; DEF-CAL-003/004 needs manual retest |

## Analyze inventory (28 audited capabilities, grouped into 9 matrix rows)

| Feature | Workspace | Implemented | Unit | GUI | Integration | Persistence | Scientific | Failure | Performance | Status | Notes / defect |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Project Result discovery/execution isolation/refresh | Analyze | yes | PASS | PASS | PASS | pointer only | N/A | PASS | PASS | PASS | Metadata-first, no raw parsing |
| Overview, provenance, Data, status handling | Analyze | yes | PASS | PASS | PASS | N/A | N/A | PASS | PASS | PASS | Result-only boundary |
| Bands, DOS, PDOS, phonon DOS | Analyze | yes | PASS | PASS | PASS | N/A | synthetic only | PASS | PASS | PASS | Real-data validation SCI-008 |
| PDOS filtering/aggregation | Analyze | yes | PASS | PASS | PASS | N/A | synthetic only | PASS | PASS | PASS | No silent cross-grid aggregation |
| Compare picker/series controls/overlay/difference | Analyze | yes | PASS | PASS | PASS | session-only | synthetic only | PASS | PASS | PASS | Exact no-interpolation policy |
| Alignment, comparison/data/image export | Analyze | yes | PASS | PASS | PASS | N/A | synthetic only | PASS | PASS | PASS | Provenance retained |
| Band edges/sample-path directness/VBM-CBM | Analyze | yes | PASS | PASS | PASS | N/A | analytic/synthetic | PASS | PASS | PASS | Never called fundamental without scope |
| Effective mass/fit preview/strain trend | Analyze | yes | PASS | PASS | PASS | N/A | analytic/synthetic | PASS | PASS | PASS | Explicit strain only |
| Relaxed structure preview/volumetric/transport/advanced interpolation | Analyze | deferred | N/A | N/A | N/A | N/A | N/A | N/A | N/A | NOT_APPLICABLE | Deliberately out of v0.1 scope |

## Automated test classification

| Subsystem | Test methods | Principal coverage |
|---|---:|---|
| Builder | 42 | view math, build operations, lattice matching, heterostructure, moiré |
| Device Builder | 40 | model, geometry, interfaces, templates, persistence/history, workspace |
| Calculate | 106 | catalog/semantics, requests, compiler/adapters, functionals/pseudos, execution, results, workflows |
| Analyze | 19 | Result-only views, comparison, derived electronic analysis, responsive/model-view QA |
| **Total** | **207** | Full offscreen unittest discovery baseline |

Project/persistence, execution, Result layer, and integration tests are embedded primarily in Calculate/Device/Analyze groups: `test_request_persistence`, `test_execution_persistence`, `test_results*`, `test_result_service`, `test_structure_handoff`, Device persistence/history, and Analyze root-pointer/discovery tests. They must be reclassified into formal QA-gate evidence during QA1–QA5, not duplicated.

## Release gates

1. All automated tests, active-source compilation, and diff checks pass.
2. No open BLOCKER or CRITICAL defect.
3. Manual core workflows pass for all four workspaces.
4. Project persistence and cross-workspace isolation pass.
5. Core QE reference scientific validation passes.
6. HSE generation/runtime validation passes, or HSE is explicitly excluded from release scope.
7. Fresh install/launcher/optional-tool/offline checks pass.
8. Documentation, defect log, and license/attribution inventory are complete.

## QA execution order

QA0 matrix/inventory → QA1 Builder → QA2 Device Builder → QA3 Calculate → QA4 Analyze → QA5 cross-workspace → QA6 scientific validation → QA7 packaging/release → QA8 release-candidate regression. These are QA phases, not feature stages.

## Release/installation and performance checks

The release plan covers fresh virtual environment, dependencies/assets/icons, first project creation, absent QE/MPI, offline pseudo cache, and dependency/license/asset/provider-attribution inventory. Performance fixtures cover startup, large structure render, large band/PDOS Result, many execution pointers, and comparison switching. Failure/data-safety coverage covers invalid structures/projects, missing tools/pseudos/MPI/workflow roots, checksum/process/cancel/recovery behavior, and isolation of Builder structure, historical request snapshots, ResultStore artifacts, and Device source structures.
