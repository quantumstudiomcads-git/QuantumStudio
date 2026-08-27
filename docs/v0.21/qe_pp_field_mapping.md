# QE 7.6 pp.x mapping used by Quantum Studio E4

| Quantum Studio property | QE 7.6 selector | QE definition | Source/canonical unit | Method boundary | Artifact | Validation |
|---|---:|---|---|---|---|---|
| Charge density | `plot_num=0` | electron pseudo-charge density | `e/bohr^3` | scalar/collinear scalar density | Gaussian cube | Si PBE |
| Spin density | `plot_num=6` | `rho(up)-rho(down)` | `e/bohr^3` | collinear only | Gaussian cube | bcc Fe PBE |
| ELF | `plot_num=8` | electron localization function | dimensionless | QE source rejects noncollinear ELF | Gaussian cube | Si PBE |
| Potential | `plot_num=11` | `V_bare + V_H` | Ry | scalar field; raw gauge retained | Gaussian cube | Si PBE |

QE 7.6 `INPUT_PP.def` and `PP/src/punch_plot.f90` are the source of these selectors. Output uses `iflag=3`, `output_format=6` (Gaussian cube). QE 7.6 `plot_num=11` V_bare+V_H is used by E5 for the vacuum asymptote: V_xc vanishes in vacuum. It remains a raw-gauge potential; E5 requires a same-state Fermi reference and a geometry/flatness-validated plateau before reporting Phi.

