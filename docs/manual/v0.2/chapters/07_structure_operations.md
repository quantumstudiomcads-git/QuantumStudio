# 7. Structure Operations

Structure operations are Builder actions on the canonical Project structure. They differ from calculations: a calculation takes a structure snapshot, whereas a confirmed Builder edit changes the Project structure and is recorded in Builder structure history.

> **Screenshot pending:** A native r28 window-capture surface was unavailable during B5.3; no substitute image was used.

## Import and export

Use Builder import to bring a supported structure into the Project. Review atom species, coordinates, cell vectors, and periodicity before continuing. Use the corresponding export control only for the format shown by the current dialog.

## Cell and atom edits

The public Builder construction/editing areas include lattice edits and atom edits where controls are shown. Supply coordinates and lattice values in the units named by the dialog. Confirm the operation and use undo/redo to inspect its effect.

## Supercells, slabs, and vacuum

- **Supercell** repeats the current cell by selected integer factors.
- **Slab** creates a surface-oriented construction from the current structure.
- **Vacuum** adjusts separation needed for non-bulk/surface modelling.

These operations can change atom count and periodic geometry substantially. Check the resulting cell and structure before scheduling a calculation.

## Nanotubes, heterostructures, and moiré structures

Builder exposes construction paths for nanotube and layered/interface work. Heterostructure and moiré tools reuse the lattice-matching system. See [Heterostructures](09_heterostructures.md) and [Moiré Structures](10_moire.md).

> **Limitation:** Exact labels and fields should be confirmed against current UI during B5.3 screenshots. This manual does not elevate internal helper names into user controls.
