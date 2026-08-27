# Quantum Studio v0.21 — E1 Electronic Capability Matrix

E1 update date: 2026-08-27. This is source, test, and bounded runtime-integration evidence; it is not a numerical-reference release claim.

Baseline: 147 public intents (20 `ready`, 1 `partial`, 126 `planned`); reconciliation maps those to 20 implemented, 1 unavailable, and 126 planned. Project files use qstudio v0.4 calculation persistence (with v0.2/v0.3 compatibility tests). The active branch is `v0.2`; v0.21 documentation is intentionally untracked until a future commit.

| ID / public name | Quantity / kind | Engine and private dependencies | Generate / execute | Parser → Result | Analyze / export | Actual status and missing work | v0.21 |
|---|---|---|---|---|---|---|---|
| `scf` / Self-Consistent Field | Ground state; total energy, Fermi (when QE prints it), total/absolute magnetization, convergence | `pw.x` | PASS / PASS | PASS → `GroundStateResult` | scalar/table/provenance; generic CSV | E1 validates the scalar contract and real QE runtime integration; forces/stress and eigenvalue/occupation artifacts remain outside GroundStateResult | E1 P0 |
| `nscf` / Non-Self-Consistent Field | Fixed-density eigenstate calculation | no public backend definition; private `qe_pw_nscf_{dos,pdos}` exists | BLOCKED public / PASS private | MISSING public result | NOT_APPLICABLE as standalone | Public catalog remains `partial`; E1 validates private purpose-signed SCF-state reuse for DOS/PDOS/Wannier, while standalone eigenvalue/result semantics remain unimplemented | E1 P0 contract |
| `relax` / Geometry Relaxation | Final energy and final atomic structure | `pw.x` | PASS / PASS | PASS → `RelaxationResult` | generic summary/table/provenance; no dedicated geometry handoff UI/export audit | Force history, final-force threshold, explicit convergence semantics and real validation missing | E2 P0 |
| `vc_relax` / Variable Cell Relaxation | Final atoms/cell, total energy | `pw.x` | PASS / PASS | PARTIAL → `RelaxationResult` (`vc_relax` flag) | generic only | Cell parsed if final `CELL_PARAMETERS` appears; pressure/stress and robust final-cell semantics absent | E2 P0 |
| `bands` / Band Structure | Path eigenvalues | SCF → `qe_pw_bands` → `bands.x` (hybrid uses SCF additional-k-points contract → `bands.x`) | PASS / PASS for validated PBE path | PASS → `BandStructureResult` | PASS plot/table/CSV/image/provenance; sampled gap/effective mass are derived | Real PBE QE 7.6 evidence exists. SOC, collinear spin, DFT+U, HSE06/B3LYP combinations each need independent validation | E3 P0 |
| `dos` / Density of States | Total DOS | SCF → dense private NSCF → `dos.x` | PASS / PASS | PARTIAL → `DOSResult` | plot/table/CSV/image | Parser reads only two numeric columns, declares energy eV but does not retain Fermi, integrated DOS, spin columns, normalization or SOC semantics; not real-validated | E4 P0 |
| `pdos` / Projected DOS | Atom/orbital components | SCF → dense private NSCF → `projwfc.x` | PASS / PASS | PARTIAL → `PDOSResult` | component filtering/aggregation, plot/table/CSV/image | Bounded `pdos_atm#*` discovery and common energy grid checks exist; spin/component column semantics, Fermi, normalization and SOC are unmodelled; no real validation | E4 P0 |
| `charge_density` / Charge Density | Real-space charge field | SCF → `qe_pp`/`pp.x` | PASS / PASS declaratively | MISSING | MISSING | No pp input content/provenance audit, no ResultService route, volumetric parser/result/viewer/export or real validation. Catalog `ready` overstates E2E state | E5 P1 |
| `spin_density` / Spin Density | Real-space magnetization field | spin SCF → `qe_pp`/`pp.x` | PASS / PASS declaratively | MISSING | MISSING | Spin guard exists. QE plot-number/collinear vs noncollinear semantics, volumetric model/parser/viewer/export are missing | E5 P1 |
| `fermi_surface` / Fermi Surface | Iso-energy surface | planned | MISSING | MISSING | MISSING | Needs dense NSCF artifact and chosen `fs.x`/Wannier contract plus mesh result/viewer | E6 P2 |
| `band_gap`, `effective_mass` | Derived sampled-path band quantities | `BandStructureResult` | NOT_APPLICABLE | PASS Qt-free analysis | PASS electronic analysis; effective-mass fit diagnostics exist | Only sampled-path scope; occupation policy required; not public run workflows | E3 P0 derived |
| `work_function` | Vacuum reference minus Fermi for slab | planned | MISSING | MISSING | MISSING | Requires planar/macroscopic potential Result, slab/vacuum contract and plateau selection; do not use vacuum maximum | E6 P1 |
| `electron_localization` / ELF | Real-space ELF | planned | MISSING | MISSING | MISSING | Requires QE pp.x quantity contract and same volumetric stack | E5 P1 |
| `charge_transfer`, `band_decomposed_charge` | Difference / selected-state density | planned | MISSING | MISSING | MISSING | Difference needs multi-system request/provenance; band-decomposed density needs state-selection contract | E6 P2 |
| `bader_charge` | Basin charges | external Bader | MISSING | MISSING | MISSING | Requires separately distributed executable, artifact contract and licensing/platform decision; QE alone is insufficient | E6 P2 |
| `magnetic_moment` | Total / absolute / projected moments | SCF stdout / projected workflow | PARTIAL | PARTIAL scalar values in `GroundStateResult` | generic scalar display | Total and absolute magnetization are parsed only if stdout prints them; no site/projected Result | E4 P1 |
| `spin_texture`, `orbital_texture`, `exchange_parameters`, `hubbard_u`, `hybrid_electronic`, `mulliken_population` | Advanced electronic properties | planned | MISSING | MISSING | MISSING | No complete workflow/result contracts; `hubbard_u` is not DFT+U input support | E6 P2 |
| `wannierization` | MLWF spread/convergence | SCF → NSCF → `wannier90 -pp` → `pw2wannier90` → `wannier90` | PASS generator/execution contract | PARTIAL → `WannierizationResult` | generic summary/provenance | Parses only final spread and number of WFs; no centres, HR, interpolated bands, or real validation | E6 P1 |

## Cross-cutting scientific findings

* Functionals registered: PZ, PBE, PW91, BLYP, HSE06, B3LYP. The QE writer emits `input_dft` and hybrid EXX controls. Registry presence is not proof that DOS/PDOS, SOC, DFT+U, or hybrid workflows are scientifically validated.
* Collinear `spin` emits `nspin=2`; SOC emits `noncolin=.true.` and `lspinorb=.true.`. Pseudopotential inspection records scalar/fully-relativistic metadata, but result parsers do not carry spin channels or SOC spinor semantics.
* No Hubbard-U request schema or QE Hubbard card writer was found. Current syntax is therefore neither confirmed legacy nor current QE syntax: DFT+U is absent.
* A generic `VolumetricResult` and a one-dimensional planar/macroscopic-field result do not exist. Required future fields include values, grid shape, cell, origin, units, quantity kind, spin/channel and source-hash provenance.
* Result artifact sources today are pw.x stdout, `bands.dat`, `dos.dat`, `pdos_atm#*`, phonon DOS, and `*.wout`; Analyze consumes `ScientificResult`, not raw engine files. pp.x cube/xsf-like output is not yet routed.
* Export is generic CSV for structured tables and plot image export for current curves. There is no volumetric export path. JSON is ResultStore persistence rather than a documented user export format.

## Recommendations

Public catalogue: keep SCF/Relax/VC-relax/Bands/DOS/PDOS user-visible. Treat NSCF as a private prerequisite by default. Do not expose raw pp.x as a successful charge/spin-density calculation until its parsed structured field is analyzable/exportable. Do not promote any public state in E1.

Shared prerequisites are deduplicated within one `ExecutionPlan` DAG; cross-request SCF/NSCF sharing is not implemented and should remain an E1 documentation boundary, not a change.

## E1 evidence and boundaries

* `GroundStateResult` is intentionally scalar-only: engine-reported total energy, optional Fermi energy/electron count/collinear magnetizations, iterations, final SCF accuracy, scientific convergence, and QE completion evidence. Optional values are omitted, never set to zero.
* QE total energy and final SCF accuracy use the shared Ry-to-eV conversion. Collinear magnetizations use `Bohr magneton/cell`, not per atom. Forces/stress remain Relax/VC-relax concerns; eigenvalues and occupations remain downstream artifact contracts.
* Private DOS, PDOS, and Wannier NSCF tasks have deterministic parent-SCF edges, immutable request snapshots, workflow-local verified pseudos, purpose-specific signatures, common QE prefix/outdir/save state, and no artificial standalone result. Public `nscf` remains `partial`.
* Runtime integration evidence: two-atom diamond-Si primitive PBE with SSSP Efficiency 1.3.0 `Si.pbe-n-rrkjus_psl.1.0.0.UPF` and QE 7.6 completed SCF -> private DOS NSCF -> dos.x. SCF parsed -22.82588915 Ry as -310.56204303437835 eV, 8.0 electrons, 5 iterations, converged=true, JOB DONE=true. Fermi and magnetizations were absent because QE did not print them. This is integration evidence, not a numerical reference.
