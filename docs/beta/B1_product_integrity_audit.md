# Quantum Studio B1 Product Integrity Audit

Generated: 2026-09-06T10:37:05.609139+00:00

## Summary

- Target catalogue count: 147
- Registered public count: 147
- Backend registry count: 44
- Architecture errors: 0
- Engine launches: 0
- Scientific statuses preserved: EPC/Eliashberg/Tc/Optical VALIDATED_UNCONVERGED; Optical Conductivity IMPLEMENTED_UNVALIDATED

## Findings

- Project and ResultStore writes use atomic replacement.
- Engine execution uses structured argv with shell=False.
- Derived optical intents deduplicate onto one dielectric workflow.
- Further scientific convergence is deferred by design for B1.
