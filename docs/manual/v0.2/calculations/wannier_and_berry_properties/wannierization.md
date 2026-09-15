# Wannierization

## Availability

| Field | Value |
| --- | --- |
| Intent ID | `wannierization` |
| Implementation | READY |
| Exposure | PUBLIC |
| Entitlement | Capability-specific; an exact per-intent plan mapping is not explicit in source. |
| Validation | UNKNOWN — implementation readiness is not a scientific-validation claim. |

## Purpose

Construct maximally localized Wannier functions.

## Physical Quantity and Theory

This source-defined Wannier90 workflow operates on the immutable Calculate structure snapshot. Its numerical interpretation depends on the configured inputs, prerequisite results, and engine output.

## When to Use It

Use this item only when its prerequisites, external tool, and compatible pseudopotentials are available. A public list entry is not an entitlement grant.

## Prerequisites

`scf`

## Required Structure State

Confirm the current Project cell, species, periodicity, and any vacuum or surface construction before compiling. Calculations never silently replace `Project.structure`.

## Engine(s) and Workflow

- **Primary engine/tool:** Wannier90
- **Workflow:** `wannier90.wannierization`
- **Execution dependencies:** the direct prerequisite intent(s) above.

## Inputs and Important Parameters

Use **Calculate** → **Configure** and **Configure XC & Pseudopotentials…** where applicable. Source-defined parameter schema: `num_wann`, `num_bands`, `projections`, `mp_grid`, `dis_win_min`, `dis_win_max`, `dis_froz_min`, `dis_froz_max`, `num_iter`, `dis_num_iter`, `spinors`, `bands_plot`, `bands_plot_format`.

> **Note:** Defaults come from the active typed configuration model. Do not treat an unshown engine default as a validated scientific setting.

## Validation Rules

Calculate validates structure, settings, pseudopotentials, engine availability, implementation state, and entitlement before execution. These are separate checks.

## Outputs, Result Type, and Plots

Declared workflow artifact(s): A dedicated output artifact is not declared by the executable definition.. A dedicated parsed result type or viewer is **NOT EXPLICIT IN SOURCE** unless Calculate/Analyze presents one after parsing. Inspect Result status and provenance before interpreting or exporting data.

## Interpretation and Convergence

Check the structure snapshot, pseudopotential provenance, numerical settings, prerequisite status, engine output, parser status, and Result status. Task completion alone does not establish scientific validation.

## Common Failures

Controlled failures include a missing prerequisite, missing/incompatible pseudopotential, unavailable external engine, invalid settings, entitlement denial, or parser/result-status issue. See [Troubleshooting](../../chapters/25_troubleshooting.md).

## Known Limitations

External engines are not claimed as bundled with the validated Windows standalone package. Exact per-intent plan mapping and scientific validation are not explicit for this entry.

## Export Options

When a parsed result is available, use the supported Calculate or Analyze export action. Do not infer a format from the engine name.

## Related Calculations

`scf`

## References

See [References](../../REFERENCES.md).
