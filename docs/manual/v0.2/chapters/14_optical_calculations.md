# 14. Optical Calculations

Quantum Studio lists public optical calculation intents with mixed implementation
state. Use the [Optical Properties reference](../calculations/optical_properties/README.md)
and each individual page to distinguish READY, PARTIAL, and PLANNED work.

The complex dielectric response is conventionally represented as:

    ε(ω) = ε1(ω) + i ε2(ω).

Derived spectra can depend on the chosen response model, energy grid,
broadening, prerequisite electronic structure, pseudopotentials, and engine
implementation. Configure only fields exposed for the selected intent and
preserve the associated execution provenance.

> **Warning:** An available optical item, engine output, or parser does not by
> itself prove physical validation for a material, convergence settings, or
> approximation. Optical validation is separate from implementation state.

The backend-only definition extinction_coefficient is not a public Calculate
intent and is not documented here as a user-selectable calculation.
