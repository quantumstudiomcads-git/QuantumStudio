# Quantum Studio v0.21 — Electronic Validation Plan (E3)

E1 runtime integration evidence used QE 7.6 discovered through Quantum Studio, direct single-process execution with OMP_NUM_THREADS=1, and the managed SSSP Efficiency 1.3.0 Si pseudo (SHA-256 ae3aefd0811f9499dbc4a72f1f9ae02ef4fc7f3568bf6f559b68668719c69e2b). A two-atom diamond-Si primitive PBE workflow completed SCF → private DOS-purpose 6x6x6 NSCF → dos.x in a temporary workflow-local pseudo directory. SCF produced JOB DONE, its convergence marker, total energy -22.82588915 Ry (-310.56204303437835 eV), and 8.0 electrons; Fermi and magnetization were correctly absent because QE did not print them. NSCF and dos.x each exited 0 with JOB DONE, reused prefix `qs_e1_si_dos`, outdir `../qe_out`, and the generated `qs_e1_si_dos.save` state. This is runtime integration evidence, not a numerical-reference validation.

| Property | Small reference | Runtime evidence | Numeric/scientific comparison |
|---|---|---|---|
| SCF / DOS / Bands | diamond Si primitive cell | QE 7.6 completes and parsers persist Results | total energy, Fermi/reference policy, band ordering/gap scope, DOS energy grid/integral convention |
| Relax / VC-relax | Si or small MgO cell | final pw.x completion | final energy, positions/cell, force/stress thresholds where implemented |
| Collinear magnetism / spin DOS/PDOS | bcc Fe (small cell) | spin-polarized QE route | total/absolute moments; channel labeling and sum consistency |
| SOC | small heavy-element semiconductor (e.g. GaAs with compatible FR pseudos) | noncolin/lspinorb route | SOC splitting; verify no false spin-up/down labels |
| DFT+U | NiO or FeO minimal validated fixture | QE Hubbard syntax accepted | declared U/orbitals, magnetic state and reference comparison |
| HSE06/B3LYP bands | Si small mesh/path | complete hybrid workflow | hybrid settings/provenance and band gap/order; separate from PBE evidence |
| Charge/spin density, ELF | small Si; bcc Fe for spin | pp.x field file exists and parses | grid/cell/unit integrity, integral/known symmetry; spin sign/channel |
| Potential/work function | symmetric clean Al(111) or Si slab with vacuum | planar/macro field result | vacuum plateau stability and Fermi-referenced work function, not field maximum |
| PDOS | Si or MgO | projwfc files discover safely | component sum/energy grid and documented normalization |
| Wannier | Si sp3 fixture | wout parsed | number of WFs, final spread and later interpolated-band agreement |
| Fermi surface | simple metal (Al) | selected backend completes | dense-grid topology/reference and mesh semantics |
| Bader | simple ionic solid (NaCl/MgO) | external executable contract | basin charges sum to valence charge within tolerance |

Runtime success (`JOB DONE`) is necessary but not sufficient. Numerical comparisons must be scoped to the actual sampled path/grid, units, spin convention, functional and pseudopotential provenance.


## E2 runtime integration evidence

E2 ran the scalar PBE Si chain through CalculationRequest, compiler, QE adapter, workflow-local pseudo provisioning, local execution, automatic ResultService parsing, ResultStore, and offscreen Analyze/export smoke. QE 7.6 used direct execution with MPI ranks 1 and OMP threads 1, a two-atom diamond-Si primitive cell, 6x6x6 SCF mesh, distinct purpose-signed 12x12x12 DOS and PDOS NSCF meshes, and SSSP Efficiency 1.3.0 Si.pbe-n-rrkjus_psl.1.0.0.UPF (SHA-256 ae3aefd0811f9499dbc4a72f1f9ae02ef4fc7f3568bf6f559b68668719c69e2b). SCF, both NSCF tasks, dos.x, and projwfc.x each exited 0 and wrote JOB DONE; all reused prefix qs_e2_si_dos_pdos, outdir ../qe_out, the SCF save state, and workflow-local pseudos. dos.x emitted 2001 monotonic samples from -10 to 10 eV with 0.01 eV spacing, total DOS, integrated DOS, and EFermi = 6.691 eV. projwfc.x emitted four Si components (atom 1/2 times s/p) with a common 1574-point grid; bounded discovery, deterministic aggregation, and CSV/SVG/PNG/PDF output were exercised programmatically. This proves runtime/artifact/parser/UI integration, not literature or numerical-reference validation.

E2 does not make a collinear-spin or SOC claim: no real spin-polarized QE output was executed in this milestone, so spin DOS/PDOS semantics are deferred to E3.


## E3 method runtime evidence

Quantum Studio QE 7.6 validation used bcc one-atom Fe with managed SSSP Efficiency PBE scalar-relativistic `Fe.pbe-spn-kjpaw_psl.0.2.1.UPF` (SHA-256 `2317a0d3b136c09b6263e1ba328b505fb1ebf33bb4b28dc3df9e39af3184ef19`) and collinear `starting_magnetization(1)=0.5`. Full SCF → private DOS NSCF → dos.x and SCF → private PDOS NSCF → projwfc.x chains completed with exit 0 and JOB DONE. SCF converged in 8 iterations and parsed total magnetization 2.89 Bohr magneton/cell. Real dos.x emitted `E,dosup,dosdw,Int dos`; real projwfc files emitted `E,ldosup,ldosdw,pdosup,pdosdw`.

A PBE+U Fe workflow with QE 7.6 `HUBBARD (ortho-atomic)` and `U Fe-3d 3.0` completed SCF → private DOS NSCF → dos.x. SCF converged in 17 iterations, parsed -328.93403679 Ry (-4475.375562272358 eV), and total magnetization 3.05 Bohr magneton/cell. This U is an integration test value, not a scientific recommendation.

A one-atom simple Te SOC SCF → Bands workflow used the bundled QE 7.6 fully relativistic PBE NC `Te.rel-pbe-n-nc.UPF` (SHA-256 `55a014358f7d98269dc977768a42b5af01fe8e2db67cc6e126da86fed964f876`), `noncolin=.true.`, and `lspinorb=.true.`. SCF, pw.x Bands, and bands.x stages completed exit 0 with JOB DONE; Results are method-labeled SOC and have no false UP/DOWN claim. These are integration, not numerical-reference, validations.


## E4 runtime integration evidence

QE 7.6 direct single-process/OMP=1 runs exercised the full Quantum Studio workflow-local pseudo, execution, automatic ResultService, ResultStore, and offscreen Analyze path. Diamond Si PBE using the managed SSSP Efficiency Si pseudo completed SCF then pp.x `plot_num=0`, `8`, and `11`; each emitted a 40×40×40 Gaussian cube and a VALID VolumetricResult. Charge density was 0.0029651–0.15244 e/bohr³ and integrated to 7.999974 electrons over the reconstructed cell (expected eight valence electrons). ELF was 0.0097371–0.99985 and dimensionless. Bare-plus-Hartree potential was -3.5408–0.71071 Ry; it is raw-gauge field evidence, not a work-function result.

Collinear bcc Fe PBE with starting_magnetization=0.5 completed SCF then `plot_num=6`; its VALID 25×25×25 spin-polarization cube ranged -0.003926 to 0.87684 e/bohr³. These are integration and artifact-format validations, not numerical-reference validation.


## E5 surface-electrostatics evidence

Al(111) scalar PBE integration run: SCF → pp.x `plot_num=11` → 30×30×360 potential cube → automatic slab/vacuum analysis. The 3-layer, 34.6765 Å cell had a 16.664 Å validated shared boundary-wrapped vacuum plateau. QE reported E_F=-1.7765 eV; E_vac=2.417519 eV with 5.28e-06 eV standard deviation and effectively zero fitted slope, yielding Phi=4.194019 eV. This is integration evidence, not a converged numerical reference value.

Final E6/E7 completion: Relax/VC parser convergence fidelity and Wannier centres/spreads/HR parsing were strengthened. No new real QE runtime calculation was launched; validated E1-E5 artifacts were reused and remaining combinations are capability-gated.
