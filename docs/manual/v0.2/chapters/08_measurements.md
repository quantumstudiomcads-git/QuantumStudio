# 8. Measurements

Builder's **Measure** area operates on the current structure selection. Use atom picking to select atoms required by the measurement, then choose an available measurement action.

Current measurement concepts include distance, angle, and dihedral measurement where the corresponding selection and Measure control are available. Quantum Studio reports geometry derived from the selected atom sequence; clear the selection before measuring a new group.

## Practical sequence

1. Open **Builder** and make the desired structure visible.
2. Pick required atoms in the order required by the measurement.
3. Use the appropriate **Measure** action.
4. Read the displayed value and unit.
5. Clear selection before starting the next independent measurement.

Distances use the structure length convention; angles and dihedrals are angular values. Inspect periodic/supercell context before interpreting a boundary-spanning measurement.

> **Screenshot planned for B5.3:** Atom-picking state, a measurement result, and the selection-clear control on a simple structure.

> **Limitation:** Measurement is inspection. It does not alter atom positions or replace a geometry-optimization workflow.
