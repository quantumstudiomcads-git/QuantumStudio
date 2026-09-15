# Refractive Index

## Availability

| Field | Value |
| --- | --- |
| Intent ID | `refractive_index` |
| Implementation | PARTIAL |
| Exposure | PUBLIC |
| Entitlement | Capability-specific; an exact per-intent plan mapping is not explicit in source. |
| Validation | UNKNOWN — implementation readiness is not a scientific-validation claim. |

## Purpose

Calculate refractive index and extinction coefficient.

## Physical Quantity and Theory

This source-defined Post-processing workflow operates on the immutable Calculate structure snapshot. Its numerical interpretation depends on the configured inputs, prerequisite results, and engine output.

## When to Use It

Use this item only when its prerequisites, external tool, and compatible pseudopotentials are available. A public list entry is not an entitlement grant.

## Prerequisites

`dielectric`

## Required Structure State

Confirm the current Project cell, species, periodicity, and any vacuum or surface construction before compiling. Calculations never silently replace `Project.structure`.

## Engine(s) and Workflow

- **Primary engine/tool:** Post-processing
- **Workflow:** `optical.independent_particle`
- **Execution dependencies:** the direct prerequisite intent(s) above.

## Inputs and Important Parameters

Use **Calculate** → **Configure** and **Configure XC & Pseudopotentials…** where applicable. Source-defined parameter schema: `energy_min_eV`, `energy_max_eV`, `number_of_points`, `interband_broadening_eV`, `intraband_broadening_eV`, `optical_k_mesh`, `optical_nbnd`, `smeartype`, `polarization_directions`, `response_model`, `carrier_regime`, `dimensionality`, `band_window_policy`, `requested_derived_properties`.

> **Note:** Defaults come from the active typed configuration model. Do not treat an unshown engine default as a validated scientific setting.

## Validation Rules

Calculate validates structure, settings, pseudopotentials, engine availability, implementation state, and entitlement before execution. These are separate checks.

## Outputs, Result Type, and Plots

Declared workflow artifact(s): A dedicated output artifact is not declared by the executable definition.. A dedicated parsed result type or viewer is **NOT EXPLICIT IN SOURCE** unless Calculate/Analyze presents one after parsing. Inspect Result status and provenance before interpreting or exporting data.

## Interpretation and Convergence

Check the structure snapshot, pseudopotential provenance, numerical settings, prerequisite status, engine output, parser status, and Result status. Task completion alone does not establish scientific validation.

## Common Failures

Controlled failures include a missing prerequisite, missing/incompatible pseudopotential, unavailable external engine, invalid settings, entitlement denial, or parser/result-status issue. See [Troubleshooting](../../chapters/25_troubleshooting.md).

## Current Implementation Limitations

This intent is catalogued **PARTIAL**. The catalogue explicitly permits partial execution and a workflow definition is present, but external-tool readiness and result handling require careful verification. Do not treat visibility as complete or scientifically validated support.

## Known Limitations

External engines are not claimed as bundled with the validated Windows standalone package. Exact per-intent plan mapping and scientific validation are not explicit for this entry.

## Export Options

When a parsed result is available, use the supported Calculate or Analyze export action. Do not infer a format from the engine name.

## Related Calculations

`dielectric`

## References

See [References](../../REFERENCES.md).
