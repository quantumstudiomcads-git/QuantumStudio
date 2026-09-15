# 9. Heterostructures

The heterostructure workflow constructs a matched multi-layer structure from compatible layer inputs. It is intended for explicit lattice-matching work, not for treating arbitrary stacked files as automatically commensurate.

## Workflow

1. Start from the Builder layered/interface construction entry point.
2. Select source layers and their order.
3. Set target relative angle and search constraints.
4. Review matching candidates, deformation/strain treatment, layer gap, vacuum, and periodic-boundary settings.
5. Choose a ranked candidate and inspect cell, atom count, z-coordinate separation, and residual mismatch before accepting it.

> **Screenshot planned for B5.3:** Two compatible layers with matching, strain, layer-gap, vacuum, and candidate-ranking controls.

## Matching concepts

For layer lattice matrices A1 and A2, a commensurate construction seeks integer transforms M1 and M2 such that transformed in-plane cells are close after requested relative rotation R(theta):

    A1 M1 ≈ R(theta) A2 M2

Residual mismatch is handled according to the selected deformation mode. Strain is a physical modelling choice, not merely a cosmetic alignment option. Review its magnitude and which layer is deformed.

## Practical interpretation

Layer gap and vacuum control out-of-plane geometry; periodic-boundary settings control how the assembled cell is interpreted. Larger determinant/search limits can yield better matches but rapidly increase cell size and downstream calculation cost.

> **Warning:** A geometrically matched cell is not proof that a functional, pseudopotential set, k-point mesh, or relaxation protocol is scientifically converged.
