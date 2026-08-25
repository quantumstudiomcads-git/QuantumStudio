# Calculate v0.1 architecture

## Canonical input direction

Calculate consumes the active native structure only through the public Project
boundary:

```text
Builder -> Project.structure -> CalculateWorkspace -> CalculationService -> compiler
```

Builder has no Calculate dependency. Calculate never reads Builder widgets,
`StructureViewport`, ASE UI state, or Device Builder state. Device-to-Calculate
is intentionally deferred.

## Current structure versus request snapshot

`CalculationService.summarize_structure(project)` reads the current
`Project.get_structure()` value whenever Calculate is refreshed. It derives only
read-only information: name, atom count, composition, PBC, cell validity, and
periodic dimensionality. Entering the Calculate workspace refreshes this summary
through ProjectWindow.

`CalculationService.create_request(...)` then copies the native `Structure` into
a `PreparedCalculationRequest`. This object keeps:

- `structure_snapshot`: independent native `frontend.core.Structure` for
  frontend/application state;
- `backend_request`: a `backend.core.CalculationRequest` containing the exact
  `Structure.to_dict()` serialization for compilation;
- the read-only input summary.

Later Builder edits therefore refresh only the current summary. They never alter
an existing request snapshot or its backend payload.

## Validation

Validation is Qt-free and belongs to `CalculationService`, not the workspace.
It verifies nonempty native structures, finite Cartesian coordinates, valid
chemical symbols, three-component Boolean PBC, and finite cell data. Workflows
that require periodic sampling (currently bands, DOS/PDOS, NSCF, and phonon
entries) additionally require a nonsingular cell and at least one periodic
direction. Calculate remains a catalog browser when no input is available, but
request preparation is disabled and reports the Builder-first empty state.

## Compiler bridge

Calculate uses the existing backend path without executing an engine:

```text
PreparedCalculationRequest
    -> RequestCompiler
    -> CalculationCompiler
    -> DependencyResolver + ParameterResolver
    -> ExecutionPlan
```

The workspace displays the resolved task order and captured structure snapshot.
The backend `CalculationCompiler` retains its legacy direct-constructor
compatibility and now consistently fills `ExecutionPlan.structure` and
`ExecutionPlan.calculation_parameters`; `RequestCompiler` reuses those resolved
values. This stage does not invoke QE, MPI, local jobs, remote systems, or
result parsing.

## Project ownership and request persistence

`.qs` format v0.4 adds an optional top-level `calculations` section:

```text
calculations
  schema_version: 0.1
  requests: [CalculationRequest, ...]
```

`Project` owns these configured backend `CalculationRequest` objects and exposes
`get_calculations()`, `get_calculation()`, `add_calculation()`,
`update_calculation()`, and `remove_calculation()`. The returned collection is
an immutable tuple; request identity uses stable UUIDs that are preserved on
save/load. Adding, updating, duplicating, or removing a request marks the
Project dirty through its existing flag.

Each persisted request contains its user-facing name, selected calculation IDs,
user parameters, execution target preference, metadata, timestamps, and one
canonical `Structure.to_dict()` snapshot. It does **not** persist an
`ExecutionPlan`, resolved defaults, dependency caches, compile status, or UI
selection. A fresh transient `PreparedCalculationRequest` and execution plan
are rebuilt when the user selects the request.

Old projects without `calculations` remain valid. v0.3 Device projects continue
to load with an empty calculation collection. Calculation records are recovered
independently: malformed records are skipped and reported through
`Project.calculation_load_errors`, while other requests, Builder structure, and
Device state remain usable.

## Configured calculation UI

Calculate has a compact persistent request list. Creation captures the current
Project structure once and stores the request in Project. Selecting a saved
request shows its snapshot and recompiles its plan without consulting the
current Builder geometry. Parameters and display name can be saved, requests
can be duplicated or removed, and **Update From Current Structure** explicitly
replaces only the selected request snapshot. Parameter edits never update
geometry implicitly.

No execution is implemented: configured and ready-for-plan are descriptive
states only. QE input generation, execution, remote systems, output parsing,
request history, result persistence, and Device-to-Calculate remain deferred.

## Catalog, executable registry, and planning DAG (C3)

The frontend catalog is discoverability metadata: stable ID, display name,
category, description, engine label, and legacy UI status. The backend
`CalculationRegistry` is the authoritative executable definition set. A Qt-free
reconciliation bridge maps catalog entries to one of three support states:
**Implemented**, **Planned**, or **Unavailable**. Only an Implemented entry with
an exact backend definition can create or compile a request. Planned and
Unavailable entries remain visible in Calculate but disable preparation with a
clear reason.

Backend definitions use one stable programmatic calculation ID. Their `requires`
fields contain direct backend calculation IDs only; request structure is the
implicit root input, while `produces` remains descriptive metadata. Registry
validation checks stable IDs, direct dependency references, self-dependencies,
parameter-schema names, prerequisite configuration references, and cycle paths.
The registry's insertion order is the documented deterministic tie-break.

Compilation builds a shared-prerequisite DAG, then performs deterministic
topological ordering by dependency level, registry order, and calculation ID.
For example, Bands + DOS produces one SCF prerequisite with edges to both target
tasks. `ExecutionPlan.tasks` contains engine-agnostic `PlannedTask` values with
stable request-local IDs (`request_id:calculation_id`), calculation ID, explicit
prerequisite task IDs, resolved parameters, a `request_snapshot` structure
reference, and workflow/engine metadata. The plan remains derived and is never
persisted.

Parameter precedence is:

1. calculation/schema defaults;
2. accuracy preset defaults;
3. workflow prerequisite defaults;
4. structure-derived defaults (currently intentionally empty);
5. explicit request parameters.

Explicit request parameters win. Shared prerequisites are resolved once from the
request-level configuration. Future workflow-specific prerequisite defaults use
`dependency_parameters`; incompatible values for the same shared prerequisite
are an explicit compiler error rather than silently creating or merging
incompatible SCF tasks.

The Calculate preview displays the deterministic task sequence together with
explicit prerequisite task IDs. It remains a planning view only: no QE input,
pseudopotential selection, engine invocation, or execution state is created.


## Quantum ESPRESSO input generation (C4)

C4 adds a strictly downstream, Qt-free engine-adapter boundary:

```text
ExecutionPlan -> QuantumEspressoAdapter -> QEGeneration -> explicit export
```

`ExecutionPlan` remains engine-agnostic and contains no QE input text or output
paths. `QuantumEspressoAdapter` derives a non-persistent `QEGeneration` of
`QETaskInput` records containing task identity, executable, directory/input and
output names, input text, and explicit task dependencies. It never invokes an
external executable.

The stable engine identifier is `quantum_espresso`. C3 definitions now use that
identifier; legacy display names are not engine identities. A request-level
`QEWorkflowContext` gives all related tasks a stable QE-safe prefix
(`qs_<request-id>`) and shared `outdir` (`../qe_out`), so SCF and a dependent
future postprocessor can reuse the same QE runtime state. `pseudo_dir` is
runtime export configuration (default `../pseudos`) rather than a machine path
persisted in a CalculationRequest.

C4 serializes `ibrav=0` geometry exclusively as `CELL_PARAMETERS angstrom` and
`ATOMIC_POSITIONS angstrom`, preserving native request-snapshot Cartesian Å
coordinates and cell values exactly. Species order is first appearance in the
snapshot; atomic masses come from ASE's periodic-table data. No geometry is
rotated, standardized, or read back from current Project structure.

A pseudopotential assignment is explicit per element, supplied as request
`pseudopotentials` parameters or to the adapter. It requires a non-empty
filename; missing or contradictory assignments raise typed domain errors.
C4 neither downloads, discovers, nor guesses pseudopotentials.

Supported C4 generators are `scf` (`pw.x`), `relax` (`pw.x`), `vc_relax`
(`pw.x` with `&CELL`), and `phonons` (`ph.x`). `bands` is deferred because C3
has no reliable explicit band path. `dos` and `pdos` are deferred because C3
lacks the scientifically required explicit NSCF/postprocessor stages.
`phonon_dos`, charge/spin density, dielectric, and absorption are likewise
deferred until their actual required QE stages are represented in the planning
DAG. The Calculate service exposes this adapter support separately from C3
compiler support, so the UI does not advertise deferred workflows as exportable.

The C4 k-point model intentionally supports only `K_POINTS gamma` and explicit
automatic meshes from resolved task parameters. It validates, rather than
silently changes, a non-unit mesh on a non-periodic axis. Namelist serialization
has lexical key order, Fortran booleans, deterministic floats, omission of
unset values, and typed failures for unsupported values.

Exports require an explicit user-selected root and use this layout:

```text
<output-root>/<request-id>/
  manifest.json
  001_scf/scf.in
  002_phonons/phonons.in
```

Files are written to a newly created staging directory and atomically moved into
place only after all input files and the derived manifest succeed. Existing
request export directories are refused; C4 does not recursively overwrite or
delete user output. The manifest is operational derived output containing the
engine, task graph, workflow context, and a stable SHA-256 fingerprint of
species/positions/cell/PBC. Inputs contain no timestamps and regenerate
byte-for-byte identically for the same request and runtime configuration.

Calculate offers read-only monospaced QE input previews and an explicit
**Generate QE Inputs** action for a selected saved request. Export neither
executes nor discovers `pw.x`, `ph.x`, MPI, schedulers, SSH, or any engine
binary. Those concerns remain C5 work.

## Internal workflow tasks and Wannier90 (C5A)

The 147 catalog entries remain public scientific intents. A public entry may
expand to private `PlannedTask` stages; those IDs are never added to the
catalog. Tasks now carry semantic task type, engine ID, tool ID, deterministic
parameter signature, explicit task edges, structure reference, and declared
artifact inputs/outputs. Signatures include resolved scientific parameters, so
an NSCF for a Wannier uniform mesh cannot be deduplicated with an incompatible
NSCF purpose or mesh.

`wannierization` is now the thirteenth backend-executable public definition. It
compiles into `scf -> qe_pw_nscf -> wannier90_preprocess -> qe_pw2wannier90 ->
wannier90_run`. The signed private NSCF task uses `pw.x`, `calculation='nscf'`,
the explicit uniform `mp_grid`, `nbnd=num_bands`, and the same QE prefix/outdir
as SCF. It declares wavefunction/eigenvalue outputs. Wannier preprocessing
uses `wannier90.x -pp <seed>` and declares `.nnkp`; pw2wannier90 declares
`.amn`, `.mmn`, and `.eig`; the main Wannier task declares `<seed>_hr.dat` and
centres. These are contracts for a future executor, not verified files.

`wannier90` is the stable second engine ID. Typed `WannierInputSettings`
requires `num_wann`, `num_bands`, explicit projections, and `mp_grid`, and
validates energy windows and iteration counts. The deterministic `.win` writer
preserves request geometry in angstrom `unit_cell_cart`/`atoms_cart`, writes the
same unshifted uniform grid represented by QE `K_POINTS automatic`, and emits
projections and optional spinor/disentanglement settings. `pw2wannier90.x`
input shares QE prefix/outdir and writes AMN/MMN. Preprocess/main command forms
are derived metadata only.

C5A exports all task directories through the existing transactional manifest
workflow. The manifest is multi-engine and records engine/tool/type, task IDs,
edges, artifact contracts, and inputs. Future execution will stage declared
artifacts between task directories; C5A executes nothing. `wannier_bands` and
all Berry/topology/Hall public objects remain deferred because no reliable
k-path or downstream post-processing workflow is represented.

## EPW electron-phonon workflow (C5B)

`electron_phonon` is a supported public intent that expands privately into a
shared SCF root, compatible Wannier NSCF/localization chain, `qe_ph_epw`, and
`epw_run`. EPW is a distinct `epw` engine with `epw.x` tool identity. Its typed
settings distinguish `nk_coarse`, `nq_coarse`, `nk_fine`, and `nq_fine`; the
Wannier `mp_grid` must equal `nk_coarse`. DFPT uses one bounded `ldisp` q-grid
task and declares dynamical-matrix/dvscf/q-point artifacts. EPW consumes QE,
Wannier, and DFPT contracts externally (`wannierize=.false.`), declaring base
coupling data and future scattering-rate artifacts. Eliashberg and Tc remain
deferred. No engine or staging operation is executed.


## BoltzTraP2 transport workflow (C5C)

C5C adds deterministic configuration-only BoltzTraP2 workflows for Boltzmann bands, Seebeck, electrical conductivity, electronic thermal conductivity, carrier concentration, and power factor. Public intents expand to private `scf -> qe_pw_nscf_btp2 -> btp2_interpolate -> btp2_transport` stages; bands stop at interpolation. The signed QE transport NSCF uses explicit dense uniform transport mesh and num_bands, is incompatible with Wannier, EPW, DOS, and optical NSCF signatures, and declares `ElectronicBandsData` for future k-points, eigenvalues, reference energy, direct and reciprocal cells, occupations/electron count, and spin information. No numerical arrays are fabricated.

The cross-engine exporter emits deterministic Quantum Studio-owned `btp2_config.json` and `btp2_transport.json` plus future Python API metadata. It neither invokes BoltzTraP2 nor parses results. Typed settings retain independent temperature (K), chemical-potential (eV), and carrier-concentration (cm^-3) grids, interpolation controls, spin/SOC, relaxation-time model, and optional 2D effective thickness. Unspecified tau yields `SIGMA_OVER_TAU`, `KAPPA_E_OVER_TAU`, and `POWER_FACTOR_OVER_TAU`; positive constant tau yields `SIGMA`, `KAPPA_E`, and `POWER_FACTOR`. EPW scattering time is reserved.

For [True, True, False], kz must be one and vacuum is never inferred as material thickness. Absolute 2D conductivity-type coefficients require explicit effective thickness; raw quantities retain normalization metadata. ZT remains deferred pending lattice thermal conductivity, and mobility remains deferred pending a physical scattering-time source such as future EPW lifetimes.

## NEGF transport architecture (C5D)

C5D adds a standalone Qt-free multi-component `TransportInput` contract: independent left/right electrodes and central region, Hamiltonian and optional overlap artifact references, principal layers, transport direction, and transverse periodicity. Existing C5A `wannier_hr` remains the semantic Wannier Hamiltonian artifact. The private graph is electrode preparation, self energies, device Green function, and transmission; it declares artifacts only.

Energy grid and eta are explicit eV settings; temperatures are K; chemical potentials are eV; transverse k meshes are PBC-consistent; and spin degeneracy is explicit. Deterministic `negf_config.json` records `execution_backend: not_selected`, with no executable, API, solver, matrix inverse, or result parsing. All public NEGF intents remain planned pending `Device -> TransportInputAdapter -> TransportInput -> NEGF compiler`; a single Builder structure is never silently treated as a device.

## Cross-engine workflow consolidation (C5E)

C5E freezes the 147-object public taxonomy through a Qt-free semantic map of calculation kind, input cardinality, scientific prerequisites, workflow family, capability constraints, and support state. Public intents never become private executable stages. The map marks single-structure, multi-structure, device-transport, trajectory, result-only, and meta-child inputs so unsupported future request models are explicit.

All engines use the generic PlannedTask contract. C5E adds stable engine descriptors, common artifact aliases/locality, producer-consumer DAG validation, workflow-builder descriptors, C6-facing manifest task contracts, and structural CommandSpec records. Tool identity is separate from engine identity, and execution readiness is declarative only. Calculate prepares/executes/parses future Results; Analyze remains responsible for visualization and interactive analysis. No engine runs in C5E.

## Generic local execution (C6)

C6 consumes the C5E `GeneratedWorkflow` contract through a Qt-free `LocalExecutionManager`. It executes one dependency-ready task at a time using validated structured `CommandSpec` data and `shell=False`; it does not branch on a calculation or engine name. Preflight validates generated manifests, root-contained task paths, inputs, dependencies, external artifact declarations, and local tool/backend availability. Local tools resolve from explicit application configuration, engine directories, then `PATH`; paths are never stored in CalculationRequests.

Runtime tasks move through PENDING, READY, RUNNING, COMPLETED, FAILED, CANCELLED, and BLOCKED. stdout/stderr remain separate task files, cancellation targets only the owned child process/process group, and optional timeout fails that task. The Calculate view selects an already generated workflow, preflights it, and runs it asynchronously so the UI remains responsive. C6 does not run MPI/HPC/remote jobs, parse science, infer artifact copy commands, register the BTP2 Python API, or select an NEGF backend. A zero exit code is process success only; convergence/result parsing remains C8.

## C7 persistent runtime recovery

C7 stores versioned execution-attempt sidecars atomically beneath generated workflow roots, never inside `.qs`. Persist request/workflow/input provenance and attempt-aware log paths; stale RUNNING records recover only as retryable INTERRUPTED and must never reattach to prior PIDs or auto-resume. Retry/restart must remain generic GeneratedTask/CommandSpec execution and preserve historical logs.

## C8A computational post-processing

C8A adds private QE post-processing stages for explicit bands (`pw.x` bands plus `bands.x`), DOS (`pw.x` dense signed NSCF plus `dos.x`), PDOS (`projwfc.x`), pp.x charge/spin raw grids, and phonon DOS (`ph.x -> q2r.x -> matdyn.x`). They remain Calculate workflow tasks and produce raw semantic artifacts only; C8B will parse them. Band paths are explicit fractional request data and are never inferred. Uniform NSCF tasks carry purpose signatures, preventing accidental sharing with Wannier, EPW, or BTP2. QE postprocessors retain the shared prefix/outdir and normalize to generic CommandSpec tasks; C6/C7 dispatch/recovery needs no engine-specific branch.

## C8B scientific result parsing

C8B adds a Qt-free engine-neutral Result model and sidecar ResultStore. Parsers consume declared raw artifacts, retain source hashes/provenance and distinguish scientific validity from process state. Current conservative parsing supports QE SCF stdout, bands, DOS, and matdyn phonon-DOS raw rows. No parser shifts energy references, mutates Builder, renders plots, or treats BTP2/NEGF configuration as numerical results.

## C8D Calculate operation

Calculate exposes a schema-driven parameter dialog over the C3 resolver with Fast, Intermediate, Precise, and Custom modes. It presents user-facing labels/units, retains explicit Custom values, and shows resolved parameter JSON before saving a request. Machine executable paths remain in Local Tools, not scientific forms. C8D adds no plotting or Analyze behavior.
