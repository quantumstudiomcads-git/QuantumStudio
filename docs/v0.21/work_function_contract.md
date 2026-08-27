# Quantum Studio v0.21 — Work Function contract (E5)

Quantum Studio computes a work-function estimate only for a slab with exactly one non-periodic lattice direction, unless an explicit X/Y/Z override is supplied. The private workflow is SCF → pp.x `plot_num=11` → potential cube → VolumetricResult → derived planar/vacuum analysis → WorkFunctionResult.

QE 7.6 `plot_num=11` is `V_bare + V_H`, in Ry. Its vacuum asymptote is appropriate for the conventional Fermi-referenced surface estimate because the exchange-correlation contribution vanishes in vacuum; raw potential remains untouched in Ry and the derived profile uses the shared Ry-to-eV constant.

A work function is reported only as `Phi = E_vac - E_F` when the parent SCF is VALID, contains a QE-reported Fermi energy, shares request/execution/structure/method provenance with the potential, and the geometry-derived atom-free region contains a flat, sufficiently wide plateau. Missing Fermi, ambiguous PBC, charged slab, narrow vacuum, or an excessive plateau slope/variation yield a conservative partial/unavailable analysis rather than fabricated values.

Vacuum geometry uses atom centers expanded by a documented 1.2 Å exclusion margin along the selected lattice axis. The largest circular atom-free interval is used; its central 60 percent is the automatic plateau candidate. Default minimum width is 5 Å, maximum standard deviation 0.05 eV, and maximum slope 0.02 eV/Å. Boundary-wrapped vacuum is represented once as a shared plateau, not duplicated as two artificial surfaces. Manual interval selection is supported by the Qt-free analysis API and marked `MANUAL`.

Macroscopic averaging is optional. It is a periodic convolution with a user-supplied physical Å window, never a fixed point-count moving average. It does not replace the planar curve. Semiconductors/insulators without an engine Fermi reference, noncollinear/SOC field variants, charged slabs, ionization potentials, electron affinities, plateau convergence studies, and dipole corrections remain outside E5.

The Al(111) validation below is integration evidence only, not a converged PBE reference value.

