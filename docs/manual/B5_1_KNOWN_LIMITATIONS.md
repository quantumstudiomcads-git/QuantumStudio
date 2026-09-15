# B5.1 Known Limitations

This list distinguishes current product limits from deferred integration work.
It is not a defect list and must be kept separate from claims of current public
functionality.

## Product and catalogue limitations

- The public Calculate catalogue has 148 intents, but public discoverability is
  broader than executable support. Only 29 entries are catalogued `ready`; 17
  are `partial`, 101 are `planned`, and one requires an external backend.
- Planned intents remain non-executable regardless of plan entitlement.
- The backend registry contains 45 definitions; `extinction_coefficient` is a
  backend-only derived definition, not a public catalogue calculation.
- Some source capabilities/results exist behind generic infrastructure without
  a dedicated per-intent public form or result viewer. B5.2 must describe them
  as internal or unknown until a public path is verified.
- Relaxation does not silently update `Project.structure`; explicit promotion
  of a relaxed geometry is not current behavior.

## Scientific-validation limitations

- B5.1 does not assign per-intent scientific validation labels where source has
  no explicit field. Catalogue implementation status and validation status are
  distinct.
- Vibrational Γ phonons, phonon DOS, and phonon band structure are distinct
  public concepts and must not be collapsed into one feature.
- EPC/Eliashberg/superconducting-Tc work must be described cautiously. Current
  records identify convergence/resource limitations rather than a general
  validated end-user superconductivity workflow.
- Optical rows may have partial implementation/execution support; physical
  validation must not be inferred from an available UI item or parser.
- Analyze only works from parsed provenance-bearing Results; it is not a raw
  engine-output browser.

## Windows, installation, and external-engine limitations

- r28 is a validated standalone application bundle, not a completed end-user
  installer/licensing integration.
- Scientific engines are not claimed as bundled with r28. Quantum ESPRESSO and
  other tools use external/local discovery or workflow-specific configuration.
- Authenticode and installer integration are post-B4 work.
- QuantumStudioRuntime and managed WSL runtime are future architecture, not a
  currently installed/public runtime product.
- The native Quantum Studio DFT engine is future/on hold until after public
  beta; it must not be presented as an engine choice.

## Licensing and server limitations

- Current client licensing is intentionally fail-closed and supports safe local
  status/enforcement, not a production account/billing experience.
- Production signing-key/KMS, HTTPS licence issuance, OIDC Authorization Code
  + PKCE, billing, student verification, organization administration,
  server-authoritative seats/sessions, trial authority, and payment-credit logic
  are deferred.
- Device Builder is gated: Free Starter, Student, Plus, and Plus Trial do not
  receive it; Pro and Organization do. A disabled/denied UI is not evidence of
  an unlock path.

## Data, privacy, and support limitations

- `.qs` persists configured request source state and opaque execution-root
  references, not a portable embedded engine/result archive.
- Cross-machine availability of external workflow roots depends on the stored
  host path and available data; it is not guaranteed by `.qs` alone.
- Diagnostics deliberately omit project/scientific files and secrets. They are
  for safe support metadata, not full scientific reproducibility archives.
- Logging is best-effort: inability to create a log root must not prevent basic
  GUI startup.

## Explicitly deferred post-beta work

- QHA/Wannier-Berry scope not publicly executable today.
- Public NEGF/device-transport execution.
- DEVSIM integration.
- Complete installer/runtime packaging and server-backed commercial flows.
