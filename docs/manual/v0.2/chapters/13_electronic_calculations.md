# 13. Electronic Calculations

Electronic workflows begin from a physically appropriate Structure,
pseudopotential assignment, and convergence settings. The public electronic
family includes self-consistent and non-self-consistent work, band/DOS
analysis, density-derived quantities, magnetic/spin-sensitive paths, and
post-processing. Exact availability is listed in the
[Electronic Properties reference](../calculations/electronic_properties/README.md).

## Self-consistent field context

The Kohn-Sham problem is commonly written as:

    [-1/2 ∇² + V_eff[n] of r] ψ_i(r) = ε_i ψ_i(r)

with electron density:

    n(r) = Σ_i f_i |ψ_i(r)|².

Operationally, an SCF calculation starts from a density, constructs an
effective potential and Hamiltonian, solves for states, forms a new density,
mixes it with the prior density, and repeats to a convergence criterion.
Quantum Studio exposes the resulting workflow through the public SCF intent and
typed settings such as functional, pseudopotentials, cutoffs, occupations,
smearing, spin treatment, SOC, and Hubbard-related controls where supported.

## NSCF, bands, and density of states

An NSCF calculation evaluates states using an established potential rather than
updating the density self-consistently. Band structure follows eigenvalues
epsilon_n(k) along a selected path. A conceptual density of states is:

    D(E) = Σ_n,k δ(E - ε_nk).

PDOS resolves density of states by chosen atomic/orbital projection. Use the
dedicated page for each public intent rather than assuming a generic DOS
workflow covers projected results, charge density, spin density, or Fermi
surface analysis.

> **Screenshot planned for B5.3:** An implemented SCF configuration and a band
> path configuration with only current visible controls.

## Practical checks

Check periodicity, k sampling/path, cutoff convergence, occupations/smearing,
pseudopotential compatibility, spin/SOC treatment, and prerequisite result
status. A plotted band gap or DOS is an analysis result, not a substitute for a
convergence study.
