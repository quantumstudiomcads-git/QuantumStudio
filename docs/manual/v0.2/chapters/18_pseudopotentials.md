# 18. Pseudopotentials

Use **Calculate → Configure XC & Pseudopotentials…** to review functional and
species-specific pseudopotential assignment. Quantum Studio supports trusted
provider resolution and **Import UPF…** for manual import, with recommended
cutoffs, functional compatibility checks, and provenance/integrity handling.

## Recommended practice

1. Confirm each structure species has an appropriate pseudopotential.
2. Keep the exchange-correlation functional consistent with the selected
   pseudopotential family.
3. Review recommended cutoffs, then perform convergence checks appropriate to
   the system and calculation.
4. Confirm provider/checksum status before generating inputs.
5. Retain result provenance when comparing calculations.

Pseudopotentials are cache-first and workflow-local materialization copies are
verified. Missing, incompatible, or integrity-invalid pseudopotentials block
input generation rather than silently substituting a file.

> **Note:** Provider-controlled automatic acquisition is implemented where
> configured and network access is available. It is not a promise that every
> pseudopotential or arbitrary URL can be downloaded automatically.

> **Screenshot pending:** A native r28 window-capture surface was unavailable during B5.3; no substitute image was used.
