# 16. Transport Calculations

Public Boltzmann transport work is catalogued under
[Boltzmann Transport](../calculations/boltzmann_transport/README.md). Current
source-defined workflows use BoltzTraP2 where implemented and depend on
appropriate electronic-structure prerequisites.

In semiclassical transport notation, electrical conductivity sigma, Seebeck
coefficient S, and electronic thermal conductivity kappa_e are transport
coefficients derived from band velocities, occupation derivatives, temperature,
and the selected relaxation-time convention. Quantum Studio makes no universal
material-independent convergence claim for these quantities.

## Operational considerations

- Review the direct SCF/electronic prerequisite named on the calculation page.
- Use the declared transport mesh, temperature, chemical-potential,
  carrier-concentration, interpolation, relaxation-time, thickness, spin, and
  SOC settings only where they are exposed.
- Verify a compatible external BoltzTraP2 tool/workflow is available.
- Interpret three-dimensional scalar results only within their documented model
  and units.

READY entries are not a claim that every transport quantity is complete.
PARTIAL entries require their explicit limitations. Planned entries are not
executable.
