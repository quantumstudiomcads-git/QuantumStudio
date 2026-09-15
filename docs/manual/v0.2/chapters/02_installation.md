# 2. Installation

The currently accepted Windows distribution is the r28 validated standalone build of Quantum Studio 0.2.0. It has been tested at its original build location and after copying the complete bundle to clean, space-containing, and Unicode-containing paths.

Use the complete standalone bundle supplied for evaluation. Do not copy only QuantumStudio.exe; adjacent files contain the Qt runtime, Python runtime components, assets, and native dependencies used by the application.

## What this build establishes

- Quantum Studio starts as a Windows standalone application.
- Normal product paths may contain spaces or Unicode characters.
- The package contains application resources and required cryptography runtime.
- Project, Builder, Calculate, Analyze, Help, and diagnostics are available according to their documented product and entitlement states.

## What it does not establish

- It is not a finished end-user installer.
- It does not claim Quantum ESPRESSO, Wannier90, EPW, or BoltzTraP2 are bundled.
- It does not ship a user-facing managed QuantumStudioRuntime installation.
- It does not include a native Quantum Studio DFT engine.

When a calculation requires an external engine, configure or discover that engine in **Calculate**. See [Runtime and Engines](19_runtime_and_engines.md).

> **Limitation:** Installer integration, Authenticode, and a managed runtime experience are later work. Do not infer an installation command or a bundled engine from a catalogue item.
