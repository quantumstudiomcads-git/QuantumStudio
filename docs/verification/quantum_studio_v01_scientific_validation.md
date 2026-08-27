# Quantum Studio v0.1 scientific validation plan

QA0 defines this plan only. Do not execute QE, MPI, network provisioning, or scientific binaries in QA0. At QA6 record executable version, command, pseudopotential SHA, input/workflow fingerprints, reference source, tolerance, and result provenance for every case. Target Quantum ESPRESSO **7.5** when available; QE 7.4.1 source inspection is not runtime validation.

| ID | Reference system / scope | Validation | Status |
|---|---|---|---|
| SCI-001 | Diamond Si conventional cell, PBE SCF | Energy/convergence/parser versus archived reference | NOT_TESTED |
| SCI-002 | Diamond Si, PBE relax | Final geometry/energy and immutable relax Result | NOT_TESTED |
| SCI-003 | Diamond Si, PBE bands/DOS/PDOS | Path labels, bands.x, DOS/PDOS arrays/parser/Analyze plot | NOT_TESTED |
| SCI-004 | Diamond Si, PBE 1/2/4 core | Direct/MPI numerical consistency within stated tolerance | NOT_TESTED |
| SCI-005 | Very small semiconductor, HSE06, nqx > 1 | ADDITIONAL_K_POINTS, hybrid bands path-only extraction, no support-point contamination | NOT_TESTED |
| SCI-006 | Cached/downloaded/offline SSSP fixtures | checksum, provider/cache, XC/SOC compatibility separately from energy validation | NOT_TESTED |
| SCI-007 | Parser corpus from SCI-001–005 | SCF, relax, bands, DOS, PDOS, phonon DOS, Wannier summary, EPW summary against raw outputs | NOT_TESTED |
| SCI-008 | Synthetic plus SCI-003 arrays | Analyze Fermi/VBM alignment, PDOS aggregation, edge/directness, analytic mass, THz↔cm⁻¹, exact differences | NOT_TESTED for real data |
| SCI-009 | Small Wannier example | Generated inputs/runtime/result summary only if tools are installed | NOT_TESTED |
| SCI-010 | Small EPW-compatible example | Generated inputs/runtime/result summary only if practical and tools are installed | NOT_TESTED |

Phonon/BEC, transport, optics, volumetric fields, and any architecture-only calculation remain outside core v0.1 scientific release validation unless their structured Result path is explicitly included later. Real validation must never represent planned/architecture-only catalog entries as executed features.
