# QE 7.6 pp.x mapping used by Quantum Studio E4

| Quantum Studio property | QE 7.6 selector | QE definition | Source/canonical unit | Method boundary | Artifact | Validation |
|---|---:|---|---|---|---|---|
| Charge density | `plot_num=0` | electron pseudo-charge density | `e/bohr^3` | scalar/collinear scalar density | Gaussian cube | Si PBE |
| Spin density | `plot_num=6` | `rho(up)-rho(down)` | `e/bohr^3` | collinear only | Gaussian cube | bcc Fe PBE |
| ELF | `plot_num=8` | electron localization function | dimensionless | QE source rejects noncollinear ELF | Gaussian cube | Si PBE |
| Potential | `plot_num=11` | `V_bare + V_H` | Ry | scalar field; raw gauge retained | Gaussian cube | Si PBE |

QE 7.6 `INPUT_PP.def` and `PP/src/punch_plot.f90` are the source of these selectors. Output uses `iflag=3`, `output_format=6` (Gaussian cube). Potential is appropriate input for later planar/vacuum analysis because it is bare ionic plus Hartree, but E4 does not calculate a vacuum plateau or work function and does not claim an absolute potential gauge.

