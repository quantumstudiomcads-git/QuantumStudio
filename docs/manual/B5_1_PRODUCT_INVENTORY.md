# B5.1 Product Inventory — Quantum Studio 0.2.0

## Scope and authority

This is a code-grounded B5.1 inventory, not end-user manual prose. Current
source, the public Calculate catalogue, and accepted B1–B4 records take
precedence over earlier plans. Status words used here are **PUBLIC**, **GATED**,
**INTERNAL**, **PARTIAL**, **PLANNED**, and **FUTURE**; entitlement and
implementation state are separate.

## Product identity

| Item | Current value | Authority |
| --- | --- | --- |
| Product name | Quantum Studio | `backend/runtime/identity.py` |
| Product version | 0.2.0 | `backend/runtime/identity.py` |
| Project extension | `.qs` | `frontend/core/project.py` and Project Hub filter |
| Project schema | `qstudio`, version 0.4 | `frontend/core/project.py` |
| Project Hub footer | `Quantum Studio · v0.2.0` | `frontend/app/project_hub.py` |
| About text | Quantum Studio; Version 0.2.0; build channel | `frontend/app/help_actions.py` |

The main public name is **Quantum Studio**. **Builder** is the current
structure workspace term. `Visualizer`/`visualizer_tools` remain historical or
compatibility terminology and must not be used as the manual's product name for
Builder.

## Startup and public application tree

```text
frontend.main
├─ configure_logging()
├─ initialize_application_data()
├─ QApplication identity/theme
├─ LicensingService.production()       (fail-closed; no developer grant)
└─ Project Hub
   ├─ New Project / Open Project / Recent Projects
   └─ Project Window
      ├─ Builder
      ├─ Device Builder                 (GATED: Pro or Organization)
      ├─ Calculate
      ├─ Analyze
      └─ Help: About / Export Diagnostics / License Status
```

`initialize_application_data()` is best-effort: a user-data-directory failure
does not itself stop basic GUI startup. Licensing initialization is also
fail-closed: lack of a usable identity/lease does not create a paid grant.

## Project Hub and project files

**PUBLIC** Project Hub controls are `New Project`, `Open Project`, a recent
project list, and `Clear`. New Project asks for project name and location and
creates `<name>.qs`; Open Project filters `Quantum Studio Projects (*.qs)`.
The recent list shows up to ten existing `.qs` paths, ignores malformed entries,
and can be cleared. A corrupt project is refused through a user-actionable load
error; a broken recent item is removed rather than treated as a valid project.

`.qs` uses UTF-8 JSON and atomic replace-on-save. Version 0.4 persists project
name, canonical structure payload, optional source Device state, persisted
calculation requests, and legacy/current calculator/workflow/result/analysis
metadata. Device data and calculation records are independently recoverable:
malformed optional data does not prevent the remaining project from opening.
Derived execution plans, compiler caches, assembled Device previews, viewport
state, histories, engine binaries, and scientific runtime payloads are not
embedded. Execution roots are opaque external pointers and may be path-specific.

## Workspace inventory

| Workspace | Status | Current user-facing scope |
| --- | --- | --- |
| Builder | PUBLIC | Canonical `Structure`/`Atom` viewing, construction, editing, import/export, measurements, reciprocal/BZ tools, and structure-history undo/redo. QPainter-based renderer; ASE is only an interoperability boundary. |
| Device Builder | GATED | Project-owned multi-region Device editing, templates, placement, interface matching, preview, and independent session history. Pro/Organization only. |
| Calculate | PUBLIC, mixed support | Public selection of 148 calculation intents, configuration, compilation, input generation, local-tool discovery/configuration, execution, result parsing, and stored execution/result browsing. Individual support varies by catalogue entry. |
| Analyze | PUBLIC | Result browser, scientific plots/tables/provenance, appearance controls, data/figure export, and compatible-result comparison. Empty state directs users to run and parse Calculate results first. |

### Builder

The real Builder combines `BuilderViewMixin`, `BuilderBuildMixin`, and
`BuilderMeasureMixin`. Public/manual-relevant areas include Build, View,
Measure, structure selection, structure import, editing/history, screenshots or
export where presented by the current UI, reciprocal-space/BZ display, and
construction operations such as crystal/supercell/slab/vacuum/nanotube/layered
or interface construction. Heterostructure and Moiré reuse the shared frozen
lattice-matching API. B5.2 must verify an exact control label at screenshot
time instead of elevating internal helper names to user controls.

Canonical structures are `frontend.core.Structure` and `Atom`; UI/project
state must not be described as storing ASE `Atoms`. Builder v0.1 is frozen
inside the 0.2.0 product; this is implementation history, not a separate
product version advertised to users.

### Device Builder

The Device Builder UI is present but protected at workspace construction by
`workspace:device_builder`. Without a valid entitlement users see **Device
Builder is not available** and a Pro/Organization remediation message rather
than a hidden implicit unlock. With Pro or Organization it exposes regions,
region properties, templates, add-from-file/add-current/remove/duplicate,
translation/rotation, placement/alignment/surface alignment, repeat, device
cell fitting, overlap checks, interface matching, preview, and undo/redo.

The Device is project-owned and optional in `.qs`; region sources are canonical
structures. Device history is session-only. The assembled preview is derived;
it is not the canonical project structure and does not imply a current NEGF
execution workflow.

### Calculate flow

```text
Project structure → immutable request snapshot → public intent selection
→ typed configuration / XC and pseudopotential selection → validation
→ DAG compilation → QE input generation → local-tool preflight/execution
→ execution sidecar → result parsing → ResultStore / Calculate and Analyze
```

Calculate snapshots the current Project structure and does not mutate it.
`Update From Current Structure` is explicit. Relaxation parsing may preserve a
final structure in result metadata, but no silent promotion into
`Project.structure` is implemented. Planned public entries remain
non-executable even if a paid plan would otherwise allow the capability.

## Calculation, jobs, and results

The public catalogue has **148 unique intents** in ten source categories.
Statuses from the live catalogue are 29 `ready`, 17 `partial`, 101 `planned`,
and 1 `external_backend_required`. The executable backend registry has 45
definitions, 44 mapped to public intents; backend-only
`extinction_coefficient` is not a public catalogue entry. See
`B5_1_CALCULATION_CATALOGUE.md` for every row.

Task states are `PENDING`, `READY`, `RUNNING`, `COMPLETED`, `FAILED`,
`CANCELLED`, `BLOCKED`, and `INTERRUPTED`. Workflow states are `PENDING`,
`RUNNING`, `COMPLETED`, `FAILED`, and `CANCELLED`. A completed engine task is
not automatically a scientifically valid result. `ScientificResult` statuses
are `VALID`, `PARTIAL`, `NOT_CONVERGED`, `UNVERIFIED`, `PARSE_FAILED`, and
`STALE`; results retain parser and source-hash provenance.

The critical phonon distinction is:

| Intent | Public meaning | Current chain/result concept |
| --- | --- | --- |
| `phonons` | Γ-point phonons, not dispersion | QE DFPT `ph.x`; Gamma phonon frequencies/eigenmodes |
| `phonon_dos` | Phonon density of states | phonon prerequisite plus dense `matdyn.x` DOS branch |
| `phonon_band_structure` | q-path phonon dispersion | phonon prerequisite plus explicit-path `matdyn.x`; PhononDispersionResult |

## Engines and runtime

| Engine/tool | Current role | Public workflows | Invocation status |
| --- | --- | --- | --- |
| Quantum ESPRESSO | Primary electronic, DFPT, and many post-processing workflows | Most ready/partial QE catalogue rows | External local installation discovered/configured by Calculate; structured argv, no shell |
| Wannier90 | Wannierization/interpolation workflow | `wannierization` ready; other public Wannier/Berry rows mostly planned | External tool; workflow-specific |
| EPW | Electron–phonon workflow | `electron_phonon` partial; related advanced intents planned | External tool; native artifacts required for validated observables |
| BoltzTraP2 | Electronic transport | conductivity, Seebeck, electronic thermal transport, power factor, carrier concentration | External tool/workflow; public support varies |
| NEGF adapter | Structured future device-transport boundary | NEGF & Device Transport catalogue is public discoverability | No current public Calculate routing/executable registry support |
| ASE | Structure interoperability | Not a user-selected engine | Library boundary, not canonical project storage |
| Native Quantum Studio DFT engine | Future/on hold until after public beta | None | Not current functionality |

The accepted Windows artifact is r28 standalone. It validates the application
bundle, not a finished installer or bundled scientific-engine distribution.
QuantumStudioRuntime/managed WSL runtime code exists as future runtime
architecture, but no current user-facing QuantumStudioRuntime installation is
accepted or documented as shipping.

## Pseudopotentials, logs, and diagnostics

Calculate exposes `Configure XC & Pseudopotentials…`, automatic trusted
provider resolution and manual `Import UPF…`, recommended cutoffs, functional
compatibility checks, provider/checksum validation, and workflow-local material
copies. Pseudopotentials are cached under the production data root and selected
files retain provenance; missing or integrity-invalid files block generation.
Automatic acquisition is provider-controlled, cache-first, and not a claim that
all pseudos or arbitrary URLs are downloadable.

On Windows, production paths resolve to:

| Purpose | Production location |
| --- | --- |
| Config and recent projects | `%APPDATA%\QuantumStudio` (`recent_projects.json`) |
| Data, licensing, diagnostics, logs, workflows, pseudos | `%LOCALAPPDATA%\QuantumStudio` |
| Logs | `%LOCALAPPDATA%\QuantumStudio\logs\quantumstudio.log` |
| Licensing key/lease state | `%LOCALAPPDATA%\QuantumStudio\licensing` |
| Pseudopotential cache | `%LOCALAPPDATA%\QuantumStudio\pseudopotentials` |
| Workflow roots | `%LOCALAPPDATA%\QuantumStudio\workflows` unless configured otherwise |

Logging uses a 2 MiB rotating file with three backups. Help offers About,
Export Diagnostics, and License Status. Diagnostics export only a metadata ZIP;
project/scientific files, raw leases, private keys, tokens, billing data, and
signing material are excluded.

## Licensing experience

The current client can display safe local status, enforce feature/calculation
decisions, and remain usable for permitted project/result reading with no,
expired, or invalid entitlement. It does not ship account sign-in, billing,
student verification, organization administration, or a production licence
server UI. Device Builder is Pro/Organization-gated. Student's explicitly
granted primitives are `calc:scf`, `calc:nscf`, and `calc:phonons`; no Device
Builder grant exists for Student, Free Starter, Plus, or Plus Trial.

## Authoritative source map

| Manual chapter area | Primary source files | Secondary accepted record |
| --- | --- | --- |
| Identity/startup/Help | `backend/runtime/identity.py`, `frontend/main.py`, `frontend/app/help_actions.py` | B4 final acceptance |
| Project Hub/.qs | `frontend/app/project_hub.py`, `frontend/app/recent_projects.py`, `frontend/core/project.py` | B1/B2 records |
| Builder | `frontend/builder/workspace.py`, `frontend/builder/view/`, `frontend/builder/measure/`, `frontend/builder/brillouin_zone/` | `AGENTS.md` |
| Device Builder | `frontend/device_builder/`, `frontend/app/licensing_access.py` | B4 plan policy |
| Calculate/catalogue | `frontend/calculate/workspace.py`, `frontend/calculations/catalog.py`, `frontend/services/calculation_service.py` | B3 audit |
| Compiler/engines/results | `backend/calculations/`, `backend/compiler/`, `backend/engines/`, `backend/execution/`, `backend/results/` | architecture docs |
| Analyze | `frontend/analyze/`, `backend/analyze/` | `docs/architecture/analyze_v01.md` |
| Pseudopotentials | `frontend/calculate/functional_pseudo_dialog.py`, `backend/pseudopotentials/` | pseudopotential architecture |
| Runtime/diagnostics | `backend/runtime/paths.py`, `logging_service.py`, `diagnostics_service.py` | B2/B4 records |

## Non-current features

Do not describe as current: a final Windows installer, bundled QE/EPW/Wannier90
or BoltzTraP2 engines, QuantumStudioRuntime installation, a native Quantum
Studio DFT engine, production billing/OIDC/server administration, public NEGF
execution, or automatic promotion of relaxed geometry into the Project.
