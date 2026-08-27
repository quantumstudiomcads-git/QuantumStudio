# Quantum Studio v0.21 — E4 Electronic Capability Matrix

Final E6/E7 completion update: 2026-08-27. This is source, test, and bounded runtime-integration evidence; it is not a numerical-reference release claim.

Catalog baseline: 147 public intents (23 `ready`, 1 `partial`, 123 `planned`); reconciliation maps 23 executable definitions, with capability status refined by the final override below. Project files use qstudio v0.4 calculation persistence (with v0.2/v0.3 compatibility tests). The active branch is `v0.2`; documentation reflects the active v0.21 worktree.

| ID / public name | Quantity / kind | Engine and private dependencies | Generate / execute | Parser → Result | Analyze / export | Actual status and missing work | v0.21 |
|---|---|---|---|---|---|---|---|
| `scf` / Self-Consistent Field | Ground state; total energy, Fermi (when QE prints it), total/absolute magnetization, convergence | `pw.x` | PASS / PASS | PASS → `GroundStateResult` | scalar/table/provenance; generic CSV | E1 validates the scalar contract and real QE runtime integration; forces/stress and eigenvalue/occupation artifacts remain outside GroundStateResult | E1 P0 |
| `nscf` / Non-Self-Consistent Field | Fixed-density eigenstate calculation | no public backend definition; private `qe_pw_nscf_{dos,pdos}` exists | BLOCKED public / PASS private | MISSING public result | NOT_APPLICABLE as standalone | Public catalog remains `partial`; E1 validates private purpose-signed SCF-state reuse for DOS/PDOS/Wannier, while standalone eigenvalue/result semantics remain unimplemented | E1 P0 contract |
| `relax` / Geometry Relaxation | Final energy and final atomic structure | `pw.x` | PASS / PASS | PASS → `RelaxationResult` | generic summary/table/provenance; no dedicated geometry handoff UI/export audit | Force history, final-force threshold, explicit convergence semantics and real validation missing | E2 P0 |
| `vc_relax` / Variable Cell Relaxation | Final atoms/cell, total energy | `pw.x` | PASS / PASS | PARTIAL → `RelaxationResult` (`vc_relax` flag) | generic only | Cell parsed if final `CELL_PARAMETERS` appears; pressure/stress and robust final-cell semantics absent | E2 P0 |
| `bands` / Band Structure | Path eigenvalues | SCF → `qe_pw_bands` → `bands.x` (hybrid uses SCF additional-k-points contract → `bands.x`) | PASS / PASS for validated PBE path | PASS → `BandStructureResult` | PASS plot/table/CSV/image/provenance; sampled gap/effective mass are derived | Real PBE QE 7.6 evidence exists. E3 validates SOC Bands with fully relativistic Te; collinear Bands remain partial because QE channel exports are not yet represented separately; DFT+U and hybrid Bands remain independently unvalidated | E3 P0 |
| `dos` / Density of States | Total scalar and validated collinear DOS | SCF → purpose-signed dense private DOS NSCF → `dos.x` | PASS / PASS | PASS → `DOSResult` | PASS plot/CSV/image/provenance | E2 validates PBE scalar Si end-to-end: raw eV axis, optional `EFermi`, total DOS, optional integrated DOS, PER_CELL normalization, bounded provenance and automatic recovery. E3 validates QE 7.6 collinear Fe UP/DOWN DOS; SOC spinor DOS remains partial. | E2 P0 |
| `pdos` / Projected DOS | Atom/species/orbital components | SCF → purpose-signed dense private PDOS NSCF → `projwfc.x` | PASS / PASS | PASS → `PDOSResult` | PASS filters/aggregation/CSV/image/provenance | E2 validates real Si s/p files with bounded prefixed discovery, deterministic identities, finite compatible raw eV grids and non-mutating aggregation. E3 validates QE 7.6 collinear Fe UP/DOWN projections; SOC spinor PDOS remains partial. | E2 P0 |
| `charge_density` / Charge Density | Electron pseudo-charge density | SCF → `pp.x` (`plot_num=0`) | PASS / PASS | PASS → `VolumetricResult` | PASS slices/profiles/NPZ/CSV/image | E4 validates scalar PBE Si cube parsing, ResultStore, Analyze and export; raw unit e/bohr³ | E4 P0 |
| `spin_density` / Spin Density | Collinear rho(up)-rho(down) | collinear SCF → `pp.x` (`plot_num=6`) | PASS / PASS | PASS → `VolumetricResult` | PASS slices/profiles/NPZ/CSV/image | E4 validates bcc Fe signed collinear field; SOC/noncollinear vector magnetization remains unsupported | E4 P0 |
| `fermi_surface` / Fermi Surface | Iso-energy surface | planned | MISSING | MISSING | MISSING | Needs dense NSCF artifact and chosen `fs.x`/Wannier contract plus mesh result/viewer | E6 P2 |
| `band_gap`, `effective_mass` | Derived sampled-path band quantities | `BandStructureResult` | NOT_APPLICABLE | PASS Qt-free analysis | PASS electronic analysis; effective-mass fit diagnostics exist | Only sampled-path scope; occupation policy required; not public run workflows | E3 P0 derived |
| `work_function` / Work Function | Fermi-referenced slab vacuum estimate | SCF → private pp.x potential → derived plateau | PASS / PASS | PASS → `WorkFunctionResult` | PASS profile/CSV/image | E5 validates scalar PBE Al(111); SOC, +U, charged and semiconductor cases remain unvalidated/blocked | E5 P0 |
| `electron_localization` / ELF | Dimensionless electron localization function | SCF → `pp.x` (`plot_num=8`) | PASS / PASS | PASS → `VolumetricResult` | PASS slices/profiles/NPZ/CSV/image | E4 validates scalar PBE Si; noncollinear ELF is unsupported by QE 7.6 pp.x | E4 P0 |
| `charge_transfer`, `band_decomposed_charge` | Difference / selected-state density | planned | MISSING | MISSING | MISSING | Difference needs multi-system request/provenance; band-decomposed density needs state-selection contract | E6 P2 |
| `bader_charge` | Basin charges | external Bader | MISSING | MISSING | MISSING | Requires separately distributed executable, artifact contract and licensing/platform decision; QE alone is insufficient | E6 P2 |
| `magnetic_moment` | Total / absolute / projected moments | SCF stdout / projected workflow | PARTIAL | PARTIAL scalar values in `GroundStateResult` | generic scalar display | Total and absolute magnetization are parsed only if stdout prints them; no site/projected Result | E4 P1 |
| `spin_texture`, `orbital_texture`, `exchange_parameters`, `hubbard_u`, `hybrid_electronic`, `mulliken_population` | Advanced electronic properties | planned | MISSING | MISSING | MISSING | No complete workflow/result contracts; `hubbard_u` is not DFT+U input support | E6 P2 |
| `wannierization` | MLWF spread/convergence | SCF → NSCF → `wannier90 -pp` → `pw2wannier90` → `wannier90` | PASS generator/execution contract | PARTIAL → `WannierizationResult` | generic summary/provenance | Parses only final spread and number of WFs; no centres, HR, interpolated bands, or real validation | E6 P1 |

## Cross-cutting scientific findings

* Functionals registered: PZ, PBE, PW91, BLYP, HSE06, B3LYP. The QE writer emits `input_dft` and hybrid EXX controls. Registry presence is not proof that DOS/PDOS, SOC, DFT+U, or hybrid workflows are scientifically validated.
* E3 uses explicit scalar, collinear, noncollinear, and SOC method states. Collinear writes `nspin=2`; SOC writes `noncolin=.true.` and `lspinorb=.true.` and requires fully relativistic pseudos. DOS/PDOS preserve validated collinear UP/DOWN channels; SOC spinor DOS/PDOS semantics remain deliberately partial.
* E3 provides structured QE 7.6 Hubbard terms and the modern eV-valued `HUBBARD (ortho-atomic)` / `U species-manifold value` card. It validates Fe 3d U propagation through SCF and private DOS NSCF; J, V, and intersite terms remain absent.
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

## Final E6/E7 completion override

The following table supersedes the earlier milestone wording for user-facing v0.21 electronic capability status. `READY` requires the normal workflow and structured Result route; `EXTERNAL_BACKEND_REQUIRED` is a complete gated path only when the executable is configured.

| Public capability | Final state | Generate / Run / Parse / Analyze / Export | Limitation |
|---|---|---|---|
| SCF; Relax; VC-Relax | READY | Yes / Yes / GroundStateResult or RelaxationResult / summary+data / CSV | VC stress is final QE pressure only; no trajectory viewer |
| NSCF | PARTIAL | Internal prerequisite only | Standalone eigenvalue Result intentionally absent |
| Bands | READY scalar PBE; READY SOC PBE; PARTIAL collinear/+U/hybrid | Existing band route | Remaining combinations have no final real integration evidence |
| DOS / PDOS | READY scalar and collinear PBE; READY +U DOS | Existing purpose-signed NSCF route | SOC projection semantics PARTIAL; hybrid route UNSUPPORTED |
| Charge Density / ELF / Potential | READY scalar PBE | pp.x → VolumetricResult → field Analyze/export | Method variants not all runtime validated |
| Spin Density | READY collinear PBE | pp.x signed field | SOC/noncollinear vector field unsupported |
| Work Function | READY scalar metal slab | SCF + pp.x potential → WorkFunctionResult | Same-state Fermi, valid slab/plateau required |
| Band Gap / Effective Mass | READY derived Analyze | Bands Result → electronic analysis/export | Sampled-path scope |
| Magnetic Moments | PARTIAL | GroundState scalar values | No site/projected moment Result |
| HSE06 / B3LYP | PARTIAL | Writer and HSE direct-band route | No final runtime validation; hybrid DOS/PDOS blocked |
| Wannierization | EXTERNAL_BACKEND_REQUIRED | Full DAG + WOUT centres/spreads/HR parsing | wannier90.x must be configured; no local executable detected |
| Wannier Bands / Fermi Surface / Bader / charge transfer / band-decomposed charge / spin-orbital textures / Hubbard-U determination / Berry-topology properties | UNSUPPORTED | No v0.21 backend Result route | Hidden from runnable workflow by planned catalog state |
