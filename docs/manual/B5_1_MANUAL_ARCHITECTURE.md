# B5.1 Manual Architecture

## Editorial rules for B5.2

Use live source and B5.1 inventory files as authority. Mark capability state
separately from implementation state. Do not turn catalogue discoverability,
backend classes, or deferred runtime/server plans into a claim that users can
run a feature today. Use **Quantum Studio**, **Builder**, **Calculate**, and
**Analyze** as product terms.

## Proposed manual chapters

| # | Chapter | Purpose and authoritative source | Screens/tables/equations/cautions | Prerequisites / detail |
| --- | --- | --- | --- | --- |
| 1 | Introduction | Product scope and workstation model; `B5_1_PRODUCT_INVENTORY.md` | Feature/status table; no equations | None; concise |
| 2 | Installation | Describe only r28 standalone package and verified limits | Package/runtimes caution | 1; concise |
| 3 | First Launch | Project Hub, safe startup, licensing state | Project Hub screen | 2; task-oriented |
| 4 | Project Hub | New, Open, Recent, Clear, corrupt-file recovery | Hub/New Project screens | 3; procedural |
| 5 | `.qs` Project Files | Schema/persistence/recovery and portability caveats | persistence table; warning | 4; advanced |
| 6 | Builder | Workspace orientation and renderer/view controls | Builder overview | 5; detailed |
| 7 | Structure Operations | Public Build operations and undo/redo | operation-location table | 6; detailed |
| 8 | Measurements | Picking and current measurement controls | measurement screen; units caution | 6; procedural |
| 9 | Heterostructures | Layer/interface workflow and validation | dialog screen, matching concepts | 7; detailed; strain/matching formula only |
| 10 | Moiré Structures | Twist workflow and size limitations | dialog screen, twist formula | 9; detailed |
| 11 | Device Builder | Entitlement prerequisite and actual region workflow | granted/gated matrix; Device screen | 6, 24; detailed |
| 12 | Calculate | Catalogue, snapshot, configuration, compile/generate/run flow | Calculate overview and state flow | 5; detailed |
| 13 | Electronic Calculations | Public electronic rows from catalogue | calculation tables; Kohn–Sham/bands/DOS formulas | 12; detailed |
| 14 | Optical Calculations | Actual support states and prerequisites | optical-status table; dielectric-response formula | 12; cautious |
| 15 | Vibrational Calculations | Γ phonons vs DOS vs dispersion | three-workflow table; dynamical-matrix formulas | 12; detailed |
| 16 | Transport Calculations | BoltzTraP2 and present limitations | transport-status table; Boltzmann equations | 12; cautious |
| 17 | Other Calculation Families | Planned/public discoverability without false run claims | category/status tables | 12; reference |
| 18 | Pseudopotentials | XC/pseudo UI, source/provenance, cutoffs | pseudo dialog; integrity cautions | 12; detailed |
| 19 | Runtime and Engines | QE discovery, external tools, no shipping-installer claim | engine matrix; platform caution | 2, 12; detailed |
| 20 | Jobs | Task/workflow states and cancellation | state table | 12; operational |
| 21 | Results | Result status/provenance and parsing distinction | status table | 12; detailed |
| 22 | Analyze | Browser, plots, comparison, exports | Analyze overview/compare screen | 21; procedural |
| 23 | Export | Structure, figure, data, comparison, diagnostics paths | export table and overwrite warning | 6, 21 |
| 24 | Licensing and Plans | Policy versus currently implemented UI | plan matrix; server-deferred warning | 3; concise |
| 25 | Troubleshooting | Controlled errors, missing engines/pseudos, parsing | symptom/action table | all; operational |
| 26 | Diagnostics | Safe diagnostic archive and log privacy | Help menu screen; privacy table | 3; concise |
| 27 | Scientific Conventions | Units, coordinate conventions, status meanings | equation/units tables | 13–16; reference |
| 28 | Files and Directories | Production Windows locations only | path table; privacy warning | 2; reference |
| 29 | Known Limitations | Product, scientific, runtime, server status | limitation matrix | all; candid |
| 30 | Version History | 0.2.0 scope and accepted r28 provenance | release summary table | 1; concise |

## Calculation-page template for B5.2

Every individual calculation page must use this sequence, omitting an item only
when the source explicitly makes it inapplicable:

1. Calculation Name
2. Purpose
3. Physical quantity
4. Theory
5. When to use it
6. Prerequisites
7. Required structure state
8. Required prior calculations
9. Engine(s)
10. Workflow
11. Inputs
12. Units
13. Important parameters
14. Defaults
15. Validation rules
16. Execution dependencies
17. Outputs
18. Result type
19. Plots
20. Interpretation
21. Convergence considerations
22. Common failures
23. Known limitations
24. Export options
25. Related calculations
26. References

For unimplemented rows, the page must state **PLANNED / not executable** near
the title instead of inventing inputs, plots, or engine execution.

## Equation plan

| Chapter | Equation/concept set | Source boundary | B5.2 treatment |
| --- | --- | --- | --- |
| Builder / Scientific conventions | row-vector coordinates, reciprocal lattice, minimum image | `frontend/builder/view/math.py`, `AGENTS.md` | operational formula, define units |
| Heterostructures | lattice match, residual/strain and deformation convention | `frontend/builder/build/lattice_matching/` | operational explanation, not full derivation |
| Moiré | requested twist and commensurability relation | Builder Moiré/lattice matching | operational formula and size caution |
| Electronic | Kohn–Sham SCF, bands, DOS/PDOS | QE compiler/results | concise physical background |
| Vibrational | dynamical matrix, Γ modes, DOS, q-path dispersion | vibrational definitions/parsers | formulas plus clear workflow distinction |
| Optical | complex dielectric response and derived spectra | optical definitions/results | formula; mark support/validation limits |
| Transport | Boltzmann coefficients and relaxation-time convention | BoltzTraP2 models/results | formula and explicit units/assumptions |
| Wannier / EPW | interpolation and electron–phonon concepts | relevant engine adapters | high-level only unless current page is executable |

## B5.2 source-of-truth map

| Manual area | Primary source modules | Inventory support |
| --- | --- | --- |
| Application/project | `frontend/main.py`, `frontend/app/`, `frontend/core/project.py` | Product Inventory |
| Builder/Device Builder | `frontend/builder/`, `frontend/device_builder/` | Product Inventory, Terminology |
| Calculate/catalogue | `frontend/calculate/`, `frontend/calculations/catalog.py`, `frontend/services/calculation_service.py` | Calculation Catalogue |
| Compiler/engines/results | `backend/calculations/`, `backend/compiler/`, `backend/engines/`, `backend/results/` | Calculation Catalogue, Limitations |
| Analyze/export | `frontend/analyze/`, `backend/analyze/`, `backend/results/store.py` | Product Inventory |
| Runtime/licensing | `backend/runtime/`, `backend/licensing/`, `frontend/app/help_actions.py` | Product Inventory, Limitations |

## B5.2 acceptance guardrails

- Preserve the 148 public-intent count and phonon terminology.
- Do not call a planned intent executable because a plan includes broad access.
- Do not describe a server, billing, OIDC, installer, Authenticode, bundled
  engine pack, QuantumStudioRuntime, or native DFT engine as shipping.
- Preserve no-silent-mutation semantics for Project structure and relaxed
  structures.
- Use screenshots only after confirming their state against r28/current UI.
