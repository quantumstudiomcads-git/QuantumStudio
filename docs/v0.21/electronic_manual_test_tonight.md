# Quantum Studio v0.21 — Electronic Manual Test Tonight

Run calculations in this order. READY means the normal Calculate → Run → automatic ResultService → Analyze route is available. Integration settings are not convergence recommendations.

## 1. Scalar PBE Si — FAST

| Calculation | Expected private tasks / result | Analyze and export | Limitation |
|---|---|---|---|
| SCF | pw.x → GroundStateResult | Summary/table CSV | Fermi may be absent for fixed occupations |
| Relax | pw.x relax → RelaxationResult | Final coordinates CSV, final energy/force summary | Final structure is read-only in Analyze |
| VC-Relax | pw.x vc-relax → RelaxationResult | Final coordinates/cell/volume summary CSV | Stress parsing is limited to QE final pressure text |
| Bands | SCF → pw.x bands → bands.x → BandStructureResult | Band plot, CSV, image, band-edge/effective-mass analysis | Scalar PBE validated |
| DOS | SCF → private DOS NSCF → dos.x → DOSResult | DOS plot, CSV/image | Scalar PBE validated |
| PDOS | SCF → private PDOS NSCF → projwfc.x → PDOSResult | Filter/aggregate, CSV/image | Scalar PBE validated |
| Charge Density | SCF → pp.x → VolumetricResult | Slice/profile, NPZ/CSV/image | Scalar PBE validated |
| ELF | SCF → pp.x → VolumetricResult | Slice/profile, NPZ/CSV/image | Scalar PBE validated |
| Electrostatic Potential | SCF → pp.x → VolumetricResult | Slice/profile, NPZ/CSV/image | Raw potential is Ry |

## 2. Surface PBE Al(111) — MEDIUM

| Work Function | SCF → pp.x potential → WorkFunctionResult | Planar potential CSV/image | Requires one non-periodic PBC axis, a same-state reported Fermi level, and a flat vacuum plateau |

## 3. Collinear PBE Fe — MEDIUM

| Collinear SCF | pw.x nspin=2 → GroundStateResult | Total/absolute magnetization summary | Scalar magnetic moments only |
| Spin DOS | SCF → private NSCF → dos.x → DOSResult | Mirrored or positive channels, CSV/image | Fe validated |
| Spin PDOS | SCF → private NSCF → projwfc.x → PDOSResult | UP/DOWN filter/aggregate, CSV/image | Fe validated |
| Spin Density | collinear SCF → pp.x → VolumetricResult | Signed field slice/profile/export | Fe validated |

## 4. SOC Te — MEDIUM

| SOC SCF | pw.x noncolin/lspinorb → GroundStateResult | Summary | Requires fully relativistic pseudo |
| SOC Bands | SOC SCF → band path → bands.x | Band plot/CSV/image | Validated Te path |
| SOC DOS | SCF → SOC NSCF → dos.x → DOSResult | Total DOS plot/CSV/image | Total-only SOC semantics; no UP/DOWN |
| SOC PDOS | Block before execution | Explicit capability diagnostic | Spinor projector semantics not yet supported |

## 5. DFT+U Fe — MEDIUM

| +U SCF | pw.x with QE 7.6 HUBBARD card → GroundStateResult | Summary/provenance | Fe 3d integration validated |
| +U DOS | +U SCF → private NSCF → dos.x | DOS plot/CSV/image | Integration validated |
| +U PDOS | +U SCF → private NSCF → projwfc.x | PDOS plot/CSV/image | Fe integration validated |

## 6. Hybrid — SLOW

| HSE06 SCF | pw.x EXX route → GroundStateResult | Summary | Input/preflight contract only; use tiny Si smoke if desired |
| HSE06 Bands | direct ADDITIONAL_K_POINTS route → bands.x | Band plot/CSV if run succeeds | PARTIAL; no final real validation in this pass |
| B3LYP SCF | QE B3LYP writer/preflight | Summary if run succeeds | PARTIAL; no runtime validation in this pass |
| Hybrid DOS/PDOS | Blocked before execution | Clear compiler message | QE hybrid NSCF-dependent route intentionally unsupported |

## 7. Wannier — EXTERNAL TOOL REQUIRED

| Wannierization | SCF → private NSCF → wannier90 -pp → pw2wannier90 → wannier90 | Centres/spreads CSV; bounded HR summary | Configure wannier90.x and pw2wannier90.x first. Current machine has no wannier90.x on PATH. |

## Intentional failure checks

- SOC with a scalar-relativistic pseudo must fail before QE launch.
- Work Function on a fully periodic bulk structure must report that no slab-normal direction exists.
- Wannierization without wannier90.x must fail preflight before SCF execution.
- Fermi Surface, Bader, charge transfer, band-decomposed charge, spin texture, orbital texture, exchange parameters, and Hubbard-U determination remain explicitly gated as Partial or External Backend Required; they are not silently Ready.
