# NEGF transport architecture — v0.1 C5D

C5D is a configuration-only NEGF domain layer. It is intentionally separate from
the single-Structure `CalculationRequest`: generic two-probe transport requires
independent left electrode, central region, and right electrode contracts.

`TransportInput` is Qt-free and serializable. Each component owns a structure
snapshot contract and typed Hamiltonian source. C5D supports existing C5A
Wannier90 `wannier_hr` semantic artifacts and external tight-binding references;
it does not load matrices. The source can carry H and optional S. Missing S means
orthogonal-basis `S = I` semantics, not a generated identity matrix.

Electrodes own explicit principal layers (transport vector, repeat count, onsite
and coupling H/S artifacts), chemical potential, and temperature. The central
region owns its H/S contract and independent left/right couplings. Principal-layer
interaction-range adequacy remains a numerical validation responsibility.

The private DAG is: electrode left/right → left/right self energy → device Green
function → transmission. It declares artifacts only. Conventions are
`G^r=[(E+i eta)S_C-H_C-Sigma_L^r-Sigma_R^r]^-1`,
`Gamma=i(Sigma^r-Sigma^a)`, and `T=Tr[Gamma_L G^r Gamma_R G^a]`.
The bias convention is `V_bias=(mu_left-mu_right)/e`; no finite-bias
self-consistency or current integration occurs.

Energy grids and eta use eV; temperatures use K; chemical potentials use eV.
Transverse k sampling obeys transport direction and PBC. Spin-degenerate mode
defaults to g=2; spin-resolved/spinor modes default to g=1, preserving SOC/spinor
semantics without a universal factor of two. Configuration records
`execution_backend: not_selected`; no solver, executable, API call, matrix inverse,
result parsing, or plotting exists in C5D.

Public NEGF catalog intents remain planned. C5D deliberately does not wire Device
Builder to Calculate. The future boundary is
`Device → TransportInputAdapter → TransportInput → NEGF workflow compiler`.
