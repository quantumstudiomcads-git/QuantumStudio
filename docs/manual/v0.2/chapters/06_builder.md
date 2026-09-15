# 6. Builder

**Builder** is Quantum Studio's public structure workspace. It uses the canonical Structure and Atom model owned by the Project. ASE is an interoperability boundary for import/export and conversion; it is not canonical project storage.

## Workspace orientation

Builder combines viewing, construction, and measurement tools. The current renderer is QPainter-based. The workspace provides structure selection, structure-history undo/redo, Build, View, and Measure areas, plus reciprocal-space/Brillouin-zone display tools where available.

> **Screenshot planned for B5.3:** Builder overview with viewport, Builder controls, and a small periodic example structure.

## Viewing a structure

Open a Project and select **Builder**. Use view controls to orient the structure, inspect the unit cell and axes, and adjust available background or display settings. Selection is a Builder interaction state: clear or reset a selection before beginning a different operation or measurement.

## Building and editing

Builder offers public construction/editing entry points for importing, crystal/supercell/slab/vacuum/nanotube construction, layered/interface work, atom and lattice edits, and structure-history undo/redo. These operations work on the Project canonical structure according to the action you confirm. See [Structure Operations](07_structure_operations.md).

## Interoperability

Use available import/export controls to exchange structures with supported external formats. Validate species, cell vectors, periodicity, and coordinate conventions after import. External data may be converted through ASE, but the Project remains responsible for its canonical representation.

> **Note:** Historical source names may mention Visualizer. The current product workspace and manual term are **Builder**.
