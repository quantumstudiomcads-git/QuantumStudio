# References

This manual uses concise operational references rather than reproducing full
method derivations. The following bibliography was checked during B5.3 against
the cited primary paper or official project documentation. Engine versions and
input syntax remain workflow-specific; use the documentation shipped with, or
specified for, the external engine actually selected for a calculation.

## Electronic structure and Quantum ESPRESSO

- W. Kohn and L. J. Sham, “Self-Consistent Equations Including Exchange and
  Correlation Effects,” *Physical Review* **140**, A1133 (1965).
  DOI: [10.1103/PhysRev.140.A1133](https://doi.org/10.1103/PhysRev.140.A1133).
- P. Giannozzi *et al.*, “QUANTUM ESPRESSO: a modular and open-source
  software project for quantum simulations of materials,” *Journal of Physics:
  Condensed Matter* **21**, 395502 (2009).
  DOI: [10.1088/0953-8984/21/39/395502](https://doi.org/10.1088/0953-8984/21/39/395502).
- P. Giannozzi *et al.*, “Advanced capabilities for materials modelling with
  Quantum ESPRESSO,” *Journal of Physics: Condensed Matter* **29**, 465901
  (2017). DOI: [10.1088/1361-648X/aa8f79](https://doi.org/10.1088/1361-648X/aa8f79).
- P. Giannozzi *et al.*, “Quantum ESPRESSO toward the exascale,” *The Journal
  of Chemical Physics* **152**, 154105 (2020).
  DOI: [10.1063/5.0005082](https://doi.org/10.1063/5.0005082).
- [Quantum ESPRESSO documentation](https://www.quantum-espresso.org/documentation/)
  for current engine-specific input, output, and workflow guidance.

## Lattice dynamics, Wannier interpolation, and electron–phonon work

- S. Baroni, S. de Gironcoli, A. Dal Corso, and P. Giannozzi, “Phonons and
  related crystal properties from density-functional perturbation theory,”
  *Reviews of Modern Physics* **73**, 515–562 (2001).
- A. A. Mostofi *et al.*, “An updated version of Wannier90: A tool for
  obtaining maximally-localised Wannier functions,” *Computer Physics
  Communications* **185**, 2309 (2014).
- S. Poncé, E. R. Margine, C. Verdi, and F. Giustino, “EPW:
  Electron-phonon coupling, transport and superconducting properties using
  maximally localized Wannier functions,” *Computer Physics Communications*
  **209**, 116 (2016).
- H. Lee *et al.*, “Electron-phonon physics from first principles using the
  EPW code,” *npj Computational Materials* **9**, 156 (2023).
- [EPW documentation and project bibliography](https://docs.epw-code.org/)
  for version-specific workflows and capabilities.
- [Wannier90 documentation](https://wannier.org/documentation/) for current
  executable, input, and interface documentation.

## Transport

- G. K. H. Madsen, J. Carrete, and M. J. Verstraete, “BoltzTraP2, a program
  for interpolating band structures and calculating semi-classical transport
  coefficients,” *Computer Physics Communications* **231**, 140–145 (2018).
  DOI: [10.1016/j.cpc.2018.05.010](https://doi.org/10.1016/j.cpc.2018.05.010).

## Pseudopotentials

- Follow the provenance, exchange-correlation compatibility, recommended
  cutoffs, and redistribution terms supplied by the selected pseudopotential
  provider. Quantum Studio does not replace those provider instructions.
- The [Quantum ESPRESSO documentation](https://www.quantum-espresso.org/documentation/)
  remains the primary implementation reference for UPF use within Quantum
  ESPRESSO workflows.

## Use in this manual

These references provide scientific and engine context. They do not make a
catalogue entry executable, validate a result for a particular material, or
replace convergence testing and result-provenance review.
