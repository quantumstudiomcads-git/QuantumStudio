# Quantum Studio 0.2.0 Beta RC1 — Release Notes

## Scope

This Linux release candidate packages the Quantum Studio desktop application separately from optional scientific Engine Packs. It is an engineering RC, not a claim that every catalogue entry is scientifically validated.

## Included

- Builder and Device Builder workflows with native `Structure`/`Device` persistence.
- Calculate architecture with 147 public scientific intents, explicit workflow planning, engine gating, and ResultStore-backed execution history.
- Electronic, vibrational, transport, EPC/Eliashberg/Tc and optical workflow families according to their current implementation status.
- Optical Properties architecture: complex dielectric response and shared derived observables including refractive index, extinction coefficient, absorption, reflectivity and loss.
- `.qs` project persistence, atomic ResultStore persistence, Analyze discovery, and structured exports.
- Relocatable Linux standalone application with user-writable runtime paths.
- Separately identifiable, hash-verifiable QE/EPW Engine Pack contract.

## Status language

The catalogue is discoverability metadata, not a claim that all 147 entries are implemented or READY. Scientific statuses and limitations remain visible in provenance and documentation.

## Distribution

The target is Linux x86_64. The application starts without an Engine Pack; engine-dependent calculations are gated until a compatible pack is configured. Windows/WSL packaging is deferred.
