# Quantum Studio v0.21 — Electronic Freeze

Final pass status: automated regression and source compilation are recorded after the implementation pass. This freeze distinguishes validated runtime integration from parser/generator-only support.

| Capability | Final state | Notes |
|---|---|---|
| SCF, Relax, VC-Relax | READY | QE result route; Relax/VC parse final geometry, energy, force/pressure when emitted, and final cell/volume. |
| Public NSCF | PARTIAL | Private purpose-signed NSCF is the supported user route. |
| Scalar PBE Bands/DOS/PDOS | READY | Existing QE runtime validation. |
| Collinear DOS/PDOS/Spin Density | READY | Existing Fe runtime validation. |
| Collinear Bands | PARTIAL | Separate QE spin_component band artifacts are not yet represented. |
| SOC SCF/Bands | READY | Fully relativistic pseudo required; Te integration validated. |
| SOC DOS | READY | Total-only SOC DOS validated; no UP/DOWN channels. |
| SOC PDOS | PARTIAL | Explicitly blocked pending exact spinor projector semantics. |
| DFT+U SCF/DOS/PDOS | READY | QE 7.6 HUBBARD propagation/runtime validation. |
| DFT+U Bands | PARTIAL | Generator path exists; no final runtime validation. |
| Charge Density, ELF, Potential | READY | Existing scalar PBE pp.x validation. |
| Spin Density | READY for collinear | SOC/noncollinear vector field unsupported. |
| Work Function | READY for scalar metal slabs | Al(111) integration validation; charged/insulator cases blocked. |
| HSE06/B3LYP SCF, HSE Bands | PARTIAL | Writer/direct-band contracts exist; final runtime validation deferred. |
| Hybrid DOS/PDOS | UNSUPPORTED | Current QE/Quantum Studio hybrid NSCF route is deliberately blocked. |
| Wannierization | EXTERNAL_BACKEND_REQUIRED | Full private DAG and centres/spreads/HR parser exist; requires configured wannier90.x. |
| Fermi Surface, Bader, charge transfer, band-decomposed charge, spin/orbital texture | EXTERNAL_BACKEND_REQUIRED / PARTIAL | Explicit non-Planned catalog states; no false Ready claim. |
| Band gap/effective mass | READY as Analyze-derived Bands analysis | Sampled-path only; export available through Electronic Analysis. |
| Magnetic moment | PARTIAL | Total/absolute cell magnetization only; no site decomposition. |

No numerical-reference claim is made here. Exchange parameters and Hubbard-U determination remain external-backend requirements; SOC PDOS remains explicitly blocked.
