# Calculation semantics and execution contract — v0.1 C5E

The public catalog contains exactly 147 scientific intents. C5E assigns each one a
machine-readable `CalculationSemantics`: stable `CalculationKind` (primitive,
workflow, derived, multi-system, meta), prerequisites, workflow family, input
cardinality, and constraints. The map is authoritative scientific taxonomy, not an
executable DAG and not a Qt concern.

Single-structure requests remain valid only for intents marked `SINGLE_STRUCTURE`.
Formation/defect/surface/reaction/alignment workflows are `MULTI_STRUCTURE`; NEGF
entries are `DEVICE_TRANSPORT`; trajectory statistics are `TRAJECTORY`; sweeps and
source intents are `META_CHILD_WORKFLOW`; artifact/result-derived intents are
`RESULT_ONLY`. These classifications deliberately prevent scientific shortcuts.

Private `PlannedTask` stages remain distinct from public objects. They carry stable
task/engine/tool IDs, parameter signatures, dependency edges, artifact inputs/outputs,
parameters, input reference, and metadata. Task-family compatibility plus matching
scientific signatures is required before deduplication—especially for QE NSCF stages.

The common vocabulary maps legacy artifact spellings to concepts such as QE save,
wavefunctions/eigenvalues, Wannier Hamiltonian, EPW coupling/scattering, BTP2 transport
data, and NEGF self energies/Green functions/transmission. Artifact validation requires
an upstream dependent producer unless the semantic artifact is explicitly external.

The engine registry separates stable engine IDs from tools: QE (`pw.x`, `ph.x`,
`pw2wannier90.x`), Wannier90, EPW, BoltzTraP2 Python API, and NEGF with no selected
backend. `CommandSpec` is structural—program, argument vector, stdio files, directory,
environment, and execution mode—never a shell command and never executed in C5E.

Generated manifests are normalized for C6-facing task identity, dependencies, signatures,
artifact contracts, working directory, input/config artifact, generation support, and
execution readiness. Calculate prepares and later executes/parses Results; Analyze
visualizes, compares, and interactively studies Results. C5E adds neither execution nor
Analyze functionality.
