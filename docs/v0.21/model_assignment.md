# Quantum Studio v0.21 — Model Assignment (E0)

| Task | Primary model / reasoning | Reason |
|---|---|---|
| E1 SCF completeness and NSCF public/private contract | Terra / High | QE/output semantics and scientific artifact contract |
| E2 DOS and PDOS end-to-end contracts | Terra / High | QE column, unit, provenance, ResultService, Analyze, and validation semantics |
| E3 collinear spin, SOC/noncollinear, and DFT+U method contracts | Terra / High | QE 7.6 method syntax, parser semantics, provenance, and real validation |
| E4 real-space volumetric fields and pp.x contracts | Terra / High | QE field semantics, units, ResultStore and Analyze validation |
| E5 surface electrostatics and work function | Terra / High | QE potential reference, slab/vacuum physics, provenance, and validation |
| E5 Analyze volumetric viewer/export | Terra / High | Qt/rendering after Result contract is fixed |
| E6 work function / planar fields / Fermi surface / Bader | Terra / High | physics-sensitive contracts and external-backend choice |
| E6 Wannier centres/interpolated bands | Terra / High | cross-engine artifact semantics |
| Qt wiring, dialogs, catalog presentation | Terra / Medium | implementation following established contracts |
| Fixture expansion, repetitive parser cases, docs | Luna / Medium | bounded mechanical work |
| Real-QE numerical validation and failure debugging | Terra / High | provenance, units, scientific interpretation |

## Explicit topic routing

SCF completeness: Terra/High; NSCF: Terra/High; Relax and VC-relax: Terra/High; Bands combinations: Terra/High; DOS and PDOS: Terra/High; SOC: Terra/High; DFT+U: Terra/High; charge/spin density and ELF: Terra/High; electrostatic potential/work function: Terra/High; Fermi surface: Terra/High; Wannier90: Terra/High; Volumetric Result: Terra/High; Analyze volumetric viewer: Terra/High; derived electronic quantities: Terra/High; real QE validation: Terra/High; documentation/testing: Luna/Medium.

This follows the requested policy: Terra establishes contracts and validates physics, Terra implements bounded established contracts and Qt/adapter work, and Luna expands tests/docs/mechanical wiring.
