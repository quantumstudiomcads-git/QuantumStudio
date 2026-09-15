# 15. Vibrational Calculations

This chapter distinguishes three different public workflows. Do not use
“phonons” as a generic name for all of them.

| Public name | Intent ID | Meaning |
| --- | --- | --- |
| Gamma-point phonons | phonons | Direct Gamma-point DFPT frequencies and eigenmodes; not a dispersion. |
| Phonon Density of States | phonon_dos | Dense q-mesh density-of-states branch built after its phonon prerequisite. |
| Phonon Band Structure | phonon_band_structure | q-path phonon dispersion built after its phonon prerequisite. |

The harmonic eigenproblem is conventionally written:

    D_κα,κ'β(q) e_κ'β(qν) = ω²_qν e_κα(qν).

Here q is a phonon wavevector, nu is a phonon branch, and omega is a phonon
frequency. Gamma-point work uses q = 0; DOS uses a mesh; a phonon band
structure uses an explicit q path. These are different inputs and different
interpretations.

## Current workflow guidance

- Select **phonons** for direct Gamma-point modes.
- Select **phonon_dos** only when a density-of-states result is required and
  the phonon prerequisite can be satisfied.
- Select **phonon_band_structure** for a dispersion along an explicit
  reciprocal-space path.

> **Screenshot planned for B5.3:** Separate Calculate selections for phonons,
> phonon_dos, and phonon_band_structure, including the path control for the
> latter.

The broader family also includes Raman, infrared, Born effective charges,
LO-TO splitting, dielectric phonon response, electron-phonon coupling, and
planned advanced vibrational work. See the
[Vibrational Properties reference](../calculations/vibrational_properties/README.md).

> **Limitation:** Earlier validation records support E1–E4 vibrational scope.
> EPC, Eliashberg, and superconducting-Tc work remains resource/convergence
> limited and must not be described as a validated end-user workflow.
