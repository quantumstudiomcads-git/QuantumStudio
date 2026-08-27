# Quantum Studio v0.21 — Model Assignment (E0)

| Task | Primary model / reasoning | Reason |
|---|---|---|
| E1 SCF completeness and NSCF public/private contract | Terra / High | QE/output semantics and scientific artifact contract |
| E2 Relax/VC-relax final-state contract | Terra / High | Geometry, cell, convergence and provenance semantics |
| E3 Bands combinations and derived quantities | Terra / High | spin/SOC/hybrid correctness and real validation |
| E4 DOS/PDOS parser and Analyze completion | Terra / High | known workflow with nontrivial column/spin/unit semantics |
| E5 VolumetricResult and pp.x field contracts | Terra / High | new scientific data model and QE quantity semantics |
| E5 Analyze volumetric viewer/export | Terra / High | Qt/rendering after Result contract is fixed |
| E6 work function / planar fields / Fermi surface / Bader | Terra / High | physics-sensitive contracts and external-backend choice |
| E6 Wannier centres/interpolated bands | Terra / High | cross-engine artifact semantics |
| Qt wiring, dialogs, catalog presentation | Terra / Medium | implementation following established contracts |
| Fixture expansion, repetitive parser cases, docs | Luna / Medium | bounded mechanical work |
| Real-QE numerical validation and failure debugging | Terra / High | provenance, units, scientific interpretation |

## Explicit topic routing

SCF completeness: Terra/High; NSCF: Terra/High; Relax and VC-relax: Terra/High; Bands combinations: Terra/High; DOS and PDOS: Terra/High; SOC: Terra/High; DFT+U: Terra/High; charge/spin density and ELF: Terra/High; electrostatic potential/work function: Terra/High; Fermi surface: Terra/High; Wannier90: Terra/High; Volumetric Result: Terra/High; Analyze volumetric viewer: Terra/High; derived electronic quantities: Terra/High; real QE validation: Terra/High; documentation/testing: Luna/Medium.

This follows the requested policy: Terra establishes contracts and validates physics, Terra implements bounded established contracts and Qt/adapter work, and Luna expands tests/docs/mechanical wiring.
