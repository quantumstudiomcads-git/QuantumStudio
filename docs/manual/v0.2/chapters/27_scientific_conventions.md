# 27. Scientific Conventions

Use the units and coordinate labels presented by the active Quantum Studio
dialog/result. Do not silently mix an engine input convention with a displayed
result convention.

| Quantity | Current manual convention |
| --- | --- |
| Direct-space coordinate | r |
| Electronic reciprocal wavevector | k |
| Phonon wavevector | q |
| Electronic band index | n |
| Phonon branch | nu |
| Energy/eigenvalue | E or epsilon, in context |
| Frequency | omega, in context |
| Temperature | T |
| Length | Angstrom where shown by Builder/results |
| Electronic energy | eV or engine-specific input unit where shown |
| Phonon frequency | cm^-1 or THz where shown by a phonon result |

## Coordinates and sampling

K-point and q-point coordinates are reciprocal-space quantities. A band or
phonon path is not interchangeable with a uniform mesh: paths support
dispersion plotting; meshes support sampling/integration such as density of
states. Inspect whether a field is fractional reciprocal coordinate, direct
coordinate, or a displayed distance along a path.

## Input choices

Convergence thresholds, cutoffs, occupations, smearing, spin treatment, SOC,
Hubbard U, temperature, pressure, and transport/optical settings have physical
and numerical consequences. Use defaults as initial values only; convergence
and model appropriateness remain the user's scientific responsibility.

For calculation-specific theory, follow the linked reference page and
[References](../REFERENCES.md).
