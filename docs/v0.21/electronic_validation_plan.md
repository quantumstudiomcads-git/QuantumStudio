# Quantum Studio v0.21 — Electronic Validation Plan (E2)

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
