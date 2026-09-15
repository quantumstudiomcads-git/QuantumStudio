# 12. Calculate

**Calculate** is the workflow workspace. It presents the public calculation
catalogue, typed configuration, validation, compilation, local-tool discovery,
execution controls, and stored execution/result access.

> **Screenshot planned for B5.3:** Calculate overview with category filter,
> calculation list/count, configured requests, and action bar.

## The calculation pipeline

    Project structure
      → immutable request snapshot
      → public intent selection
      → typed configuration and XC/pseudopotential selection
      → validation
      → workflow dependency graph compilation
      → engine input generation and local-tool preflight
      → execution sidecar
      → result parsing
      → ResultStore, Calculate, and Analyze

The current Project structure is copied into the request snapshot. **Update From
Current Structure** is explicit. A calculation does not silently mutate the
Project structure, and a relaxed output is not silently promoted into it.

## Basic workflow

1. Prepare and inspect the Project structure in Builder.
2. Open **Calculate** and select a public intent.
3. Choose **Add Selected Calculations** as appropriate.
4. Use **Configure** for typed parameters and **Configure XC &
   Pseudopotentials…** for functional/pseudopotential choices.
5. Use **Save Parameters** when you intend to preserve request changes.
6. Validate and select **Compile** or **Compile Workflow**.
7. Use **Generate QE Inputs**, **View QE Inputs**, and local-tool controls when
   the compiled workflow supports them.
8. Run only after validation and external-engine preflight succeed.
9. Inspect results through **Results…** and Analyze.

## Three separate states

| State | Question answered |
| --- | --- |
| Implementation state | Is this public intent implemented, partial, planned, or externally unavailable? |
| Entitlement state | Is the requested capability allowed for the current local entitlement? |
| Scientific validation/result state | Did this specific configured execution parse and meet its reported result status? |

These states are intentionally separate. A planned intent remains unavailable
even under broad entitlement. A permitted task can still fail an engine,
convergence, parser, or result-status check.

The catalogue has 148 public intents: 29 READY, 17 PARTIAL, 101 PLANNED, and
one EXTERNAL BACKEND REQUIRED. Use [Calculation Index](../CALCULATION_INDEX.md)
for the exact mapping.
