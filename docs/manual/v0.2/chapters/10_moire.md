# 10. Moiré Structures

A moiré structure is a twist-preserving matched layered construction. In Quantum Studio it is built through the lattice-matching foundation used by heterostructures, with a twist-angle input and resulting commensurate-cell candidate.

## Workflow

1. Open the Builder moiré construction entry point.
2. Choose layer inputs and enter the intended twist angle.
3. Review matching candidates, rotation handling, strain/deformation choice, gap, vacuum, and periodic-boundary settings.
4. Accept a candidate only after reviewing residual mismatch and cell size.

For small relative twist theta, a simple equal-lattice heuristic has a moiré length scale that grows approximately as L_M proportional to a divided by 2 sin(theta/2). This is an interpretation aid, not a promise that every requested angle is commensurate inside current search limits.

> **Screenshot planned for B5.3:** A small bilayer with twist input, matching result, and a clearly visible cell-size warning.

## Practical limits

Small twist angles can create very large cells. Large atom counts affect rendering, matching time, pseudopotential setup, k-point choices, and all subsequent engine calculations. Use constrained searches first, then verify the accepted structure visually and numerically.
