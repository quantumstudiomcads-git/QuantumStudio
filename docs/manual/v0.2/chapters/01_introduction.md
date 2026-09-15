# 1. Introduction

Quantum Studio is a project-based desktop workstation for building atomistic structures, preparing scientific workflows, running supported external-engine calculations, and inspecting parsed results. A Project relates structure, configured calculation requests, execution references, and results without treating a raw engine directory as the product interface.

| Workspace | Current role |
| --- | --- |
| **Project Hub** | Create, open, and return to recent .qs projects. |
| **Builder** | View, construct, edit, measure, and export canonical structures. |
| **Device Builder** | Build multi-region Devices when a Pro or Organization entitlement permits it. |
| **Calculate** | Select intents, configure, compile, execute supported workflows, and inspect executions. |
| **Analyze** | Inspect parsed Results through plots, tables, provenance, comparison, and export. |

Three concepts appear throughout the manual:

- **Structure** is the canonical atomistic state owned by the Project.
- **Calculation** is a public intent plus configuration and a structure snapshot.
- **Result** is parsed, provenance-bearing scientific output; it is not merely a raw engine output file.

## Availability states

| Label | Meaning |
| --- | --- |
| **READY** | Public catalogue and executable definition support a normal workflow, subject to inputs, external tools, and entitlement. |
| **PARTIAL** | Public but incomplete or limited; executable only where source explicitly permits it. |
| **PLANNED** | Publicly discoverable, but not executable in Quantum Studio 0.2.0. |
| **EXTERNAL BACKEND REQUIRED** | Publicly described but unavailable for local execution because a required backend is not composed. |

> **Warning:** A plan entitlement cannot turn a planned or unavailable implementation into an executable calculation. A completed engine process does not automatically establish a scientifically converged Result.

See [Calculate](12_calculate.md), [Results](21_results.md), and the [Calculation Index](../CALCULATION_INDEX.md).
