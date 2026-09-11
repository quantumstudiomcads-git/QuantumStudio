# Quantum Studio v0.2 — B3 Calculation Catalogue Gap Audit

## A. Scope and method

B3 audited the accepted 147-entry catalogue at `2a5b0a3` against the
authoritative backend calculation registry, dependency planner, QE adapter,
result parser routes, ResultStore, Analyze result-family routing, and the
typed Calculate parameter surface. The audit deliberately distinguishes
public user intents from private execution nodes such as `qe_ph`, `qe_q2r`,
and `qe_matdyn_*`.

Machine-readable snapshots were generated at:

- `E:\QuantumStudio-W8\reports\B3_catalogue_before.json`
- `E:\QuantumStudio-W8\reports\B3_backend_capabilities.json`

The reproducible generator is `scripts/b3_catalogue_audit.py`.

## B. Architecture

- Public catalogue: `frontend/calculations/catalog.py`
- Catalogue/backend reconciliation: `frontend/calculations/reconciliation.py`
- Backend registry and definitions: `backend/calculations/registry.py`,
  `backend/calculations/*.py`
- Semantic classification: `backend/calculations/semantics.py`
- Dependency planning: `backend/compiler/dependency_resolver.py`
- Workflow compilation: `backend/compiler/calculation_compiler.py` and
  `backend/compiler/postprocessing.py`
- Engine mapping/input generation: `backend/engines/qe/adapter.py` and
  `backend/engines/qe/postprocessing.py`
- Result parsing/routing: `backend/results/parsers.py` and
  `frontend/services/result_service.py`
- Analyze presentation: `frontend/analyze/workspace.py` and
  `frontend/analyze/plots/`

The before snapshot contained 147 public entries, 44 backend definitions, no
invalid catalogue mappings, and one backend-only derived optical capability:
`extinction_coefficient`. That capability is intentionally represented as a
derived property of the shared optical dielectric result, not as a separate
public workflow.

## C. Category summary

| Category | Before | Backend-ready gaps | Duplicates | Recommended after |
|---|---:|---|---|---:|
| Structural & Ground State | 15 | None | None | 15 |
| Electronic Properties | 20 | None | None | 20 |
| Vibrational Properties | 15 | Phonon Band Structure | None | 16 |
| Optical Properties | 15 | None; extinction is a derived optical property | None | 15 |
| Wannier & Berry Properties | 15 | None | None | 15 |
| Boltzmann Transport | 10 | None | None | 10 |
| NEGF & Device Transport | 15 | Deferred TransportInput/public routing | None | 15 |
| Molecular Dynamics | 12 | No executable MD registry | None | 12 |
| Thermodynamic & Advanced | 15 | No executable registry | None | 15 |
| Specialized & Post-processing | 15 | No executable registry | None | 15 |
| **Total** | **147** | **1** | **0** | **148** |

The many planned catalogue entries are explicit browseable roadmap items, not
backend-capable intents. They were not promoted or removed during B3.

## D. Vibrational audit — existing 15 entries

| ID | Name | Meaning | Workflow | Result | Public readiness |
|---|---|---|---|---|---|
| `phonons` | Γ-Point Phonons | DFPT frequencies/eigenmodes at Γ | `scf → ph.x` with Gamma q point | `GammaPhononResult` | READY |
| `phonon_dos` | Phonon Density of States | DOS from interpolated force constants | `scf → ph.x` q mesh → `q2r.x` → `matdyn.x` DOS | `PhononDOSResult` | READY |
| `phonon_modes` | Phonon Eigenmodes | Eigenvector analysis concept | None | None | NOT_IMPLEMENTED |
| `raman` | Raman Spectrum | Gamma Raman-active modes | `scf → ph.x → dynmat.x` | `RamanResult` | READY, restricted QE contract |
| `infrared` | Infrared Spectrum | Gamma infrared activities | `scf → born/dynmat` | `IRResult` | READY |
| `lo_to_splitting` | LO-TO Splitting | Directional non-analytic Gamma modes | `scf → born → dynmat` | `LOTOResult` | READY |
| `born_charges` | Born Effective Charges | Born tensors and electronic dielectric tensor | `scf → ph.x` polar | `BornEffectiveChargeResult` | READY |
| `dielectric_phonon` | Phonon Dielectric Response | Harmonic ionic/electronic dielectric response | `scf → born → dynmat` | `PhononDielectricResult` | READY |
| `electron_phonon` | Electron-Phonon Coupling | EPW coupling quantities | QE SCF/NSCF/Wannier/EPW chain | `ElectronPhononCouplingResult` | PARTIAL; EPW contract |
| `eliashberg` | Eliashberg Function | Electron-phonon spectral function | None | None | NOT_IMPLEMENTED |
| `superconducting_tc` | Superconducting Critical Temperature | Tc estimate | None | None | NOT_IMPLEMENTED |
| `phonon_lifetime` | Phonon Lifetime | Scattering lifetimes | None | None | NOT_IMPLEMENTED |
| `lattice_thermal_conductivity` | Lattice Thermal Conductivity | Phonon thermal conductivity | None | None | NOT_IMPLEMENTED |
| `anharmonic_phonons` | Anharmonic Phonons | Anharmonic properties | None | None | NOT_IMPLEMENTED |
| `quasi_harmonic` | Quasi-Harmonic Approximation | Temperature-dependent thermodynamics | None | None | NOT_IMPLEMENTED |

### Current `phonons` intent

`phonons` is specifically the Gamma-point primitive intent. Its default
`q_point` is `[0, 0, 0]`; `phonon_input()` emits `ldisp = .false.` and a Gamma
q point. It uses `scf → ph.x`, preserves a request structure snapshot, and
routes the terminal artifact to `QE_PHONON_GAMMA`, parsed as
`GammaPhononResult`. It is not a dispersion or DOS umbrella.

## E. Phonon Band Structure trace

Before B3, the capability was present but hidden inside the `phonon_dos`
workflow whenever optional `phonon_path` was supplied. That was an exposure
defect: selecting DOS unexpectedly produced a second dispersion result.

The existing implementation provides the complete narrow path:

`SCF → ph.x` on an explicit q mesh → `q2r.x` force constants → `matdyn.x`
high-symmetry path.

- Workflow: present in `backend/compiler/postprocessing.py`
- q mesh: typed `qmesh` controls
- q path: existing Brillouin-zone recommendation/path representation
- Path density: existing per-segment point counts
- ASR: existing `crystal` setting
- Compiler: present
- QE writer: present, emits `q_in_cryst_coord` and explicit points
- Parser: `parse_phonon_dispersion`
- Result type: `PhononDispersionResult`
- Analyze: `PhononDispersionPlot`, including q distance, labels, units, and
  negative frequencies
- LO-TO/non-analytic corrections: not part of this ordinary harmonic path;
  explicit polar workflows remain separate
- 2D/3D: uses the existing structure/path capability and does not introduce
  new partial-periodicity physics

It is now exposed as `phonon_band_structure`, with explicit path validation.
The public workflow emits dispersion only; it does not emit DOS.

## F. Phonon DOS trace

`phonon_dos` was already a real public intent and remains so. It uses:

`SCF → ph.x` on a user q mesh → `q2r.x` → `matdyn.x` dense DOS mesh.

It has typed q-mesh and DOS-mesh inputs, `PHONON_DOS_RAW_DATA` parser routing,
`PhononDOSResult`, and `PhononDOSPlot`. Its result frequency axis is cm⁻¹ with
the existing THz conversion. It no longer silently creates a dispersion
branch or requires a path.

## G. Intent comparison

| Intent | Distinct user objective? | Distinct inputs? | Distinct result? | Public entry? |
|---|---|---|---|---|
| Γ-Point Phonons | Yes — modes at one q point | Gamma q point | `GammaPhononResult` | `phonons` |
| Phonon Band Structure | Yes — dispersion along a path | q mesh, explicit path, segment density, ASR | `PhononDispersionResult` | `phonon_band_structure` |
| Phonon Density of States | Yes — frequency distribution over a dense mesh | q mesh, DOS mesh, ASR | `PhononDOSResult` | `phonon_dos` |

Band and DOS are therefore separate public intents, just as electronic Band
Structure and Density of States are separate. The previous path option under
`phonon_dos` was a misleading mixed intent and was removed from that route.

## H. All-category gap and duplicate findings

- Backend-only: `extinction_coefficient`; classified as a derived optical
  property already exposed through the shared optical result/property selector,
  not a missing standalone workflow.
- Missing public exposure: `phonon_band_structure`; fixed by one stable public
  ID and backend registration.
- Catalogue-only planned entries: the 101 roadmap/planned entries are explicit
  and not executable; they are not placeholders claiming READY support.
- Duplicate IDs: none.
- Obsolete aliases: none.
- Internal nodes exposed as public entries: none after the new separation.
- Electronic, optical, transport, MD, and remaining categories were audited;
  no additional READY public-intent gaps were found.

## I. Count and compatibility decision

BEFORE: **147**

AFTER: **148**

Delta: **+1**, `phonon_band_structure`. `phonon_dos` was already present and
was not counted twice. No existing public ID was removed or renamed. Existing
`.qs` IDs remain resolvable; the `.qs` schema was not changed.

## J. B4/B5 impact

Existing stable calculation IDs are suitable future entitlement feature keys.
The recommended B4 integration point is the capability/catalogue policy
boundary, not widget-level checks.

B5/website follow-up: update the catalogue total to 148 and document the three
distinct vibrational intents. No website repository was modified in B3.

## K. Final statuses

- Phonon Band Structure: **EXPOSED**
- Phonon Density of States: **ALREADY REPRESENTED**, with its accidental
  dispersion side effect corrected
- Catalogue scientific semantics: unchanged except for public exposure and
  routing separation of already implemented workflow branches
