# 19. Runtime and Engines

Quantum Studio coordinates external tools through structured workflow
compilation and argument-based invocation. It does not rely on shell command
strings for normal engine execution.

| Engine/tool | Current role | Distribution status |
| --- | --- | --- |
| Quantum ESPRESSO | Primary electronic, DFPT, and post-processing workflows | External local discovery/configuration; not claimed bundled. |
| Wannier90 | Wannierization and related planned work | External workflow-specific tool. |
| EPW | Electron-phonon workflow | External tool; advanced outputs have validation limits. |
| BoltzTraP2 | Supported electronic transport workflows | External tool/workflow. |
| NEGF adapter | Future structured device-transport boundary | No current public executable Calculate routing. |
| ASE | Structure interoperability library | Not a user-selected engine or project model. |

Use Calculate local-tool controls to choose an installation folder or rescan
when the relevant workflow supports it.

> **Screenshot pending:** A native r28 window-capture surface was unavailable during B5.3; no substitute image was used.

**QuantumStudioRuntime** is future installer/runtime architecture, not a
currently installed user product. A native Quantum Studio DFT engine is also
future/on hold until after public beta.
