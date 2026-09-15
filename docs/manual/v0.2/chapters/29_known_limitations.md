# 29. Known Limitations

## Product and catalogue

- The 148-item public catalogue is broader than executable support: 29 READY,
  17 PARTIAL, 101 PLANNED, and one EXTERNAL BACKEND REQUIRED.
- Planned entries remain non-executable regardless of entitlement.
- The backend-only extinction_coefficient definition is not a public calculation.
- Relaxation does not silently update Project structure; explicit promotion of a
  relaxed geometry is not current behaviour.
- Analyze uses parsed Results rather than arbitrary raw engine output.

## Scientific validation

- Implementation state is not per-intent scientific validation.
- Gamma phonons, phonon DOS, and phonon band structure are different workflows.
- EPC/Eliashberg/superconducting-Tc work has resource/convergence limits and is
  not a general validated end-user superconductivity workflow.
- Optical rows require calculation-specific validation; an exposed item or
  parser is not proof of physical convergence.

## Windows and external engines

- r28 is a validated standalone bundle, not a final installer.
- External engines are not claimed as bundled.
- QuantumStudioRuntime and a native Quantum Studio DFT engine are future work.
- Authenticode and installer integration remain post-B4 work.

## Licensing and server services

- The current client is fail-closed local enforcement, not a production
  account/billing experience.
- KMS/signing service, HTTPS licence issuance, OIDC PKCE, billing, student
  verification, organization administration, server sessions/trials, and
  payment-credit logic are deferred.

## Post-beta scope

Public NEGF/device transport, QHA/Wannier-Berry scope, DEVSIM integration, and
complete installer/runtime/server integration are not current user workflows.
