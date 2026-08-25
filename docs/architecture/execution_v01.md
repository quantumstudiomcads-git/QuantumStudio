# Local execution v0.1

C6 adds a Qt-free, serial local executor.  Engine adapters first generate their
ordinary task records and deterministic files.  The adapter boundary converts those
records into one `GeneratedWorkflow`; `LocalExecutionManager` consumes only that
contract, never calculation IDs or engine-specific classes.

`GeneratedTask` contains a task ID, dependency IDs, declared artifact contracts,
working directory, input files, and structured `CommandSpec`.  Commands are invoked
with argument arrays and `shell=False`.  Standard input is explicitly opened, and
separate standard-output and standard-error files are retained in the task directory.
Working paths must remain beneath the generated workflow root.

Tasks move through `PENDING`, `READY`, `RUNNING`, `COMPLETED`, `FAILED`,
`CANCELLED`, or `BLOCKED`.  C6 runs one ready task at a time in declared topological
order.  A failed or cancelled prerequisite blocks dependents.  Cancellation only
signals the owned child process (or its process group), then escalates after a short
grace interval.  Optional task timeouts fail the owned task.  Runtime records retain
timestamps, exit codes, log paths, and concise errors; they are not scientific input
or persistent result data.

Executables resolve in this order: an explicit local tool path, an engine-specific
directory, then `PATH`.  Machine-specific paths live in `LocalToolConfiguration`,
not in a `CalculationRequest`.  Preflight validates the manifest, task DAG, working
and input paths, executable/backend availability, and declared external artifacts.
No shell redirection, shell substitutions, MPI, scheduler, SSH, or arbitrary Python
source is accepted.

QE (`pw.x`, `ph.x`, `pw2wannier90.x`), Wannier90, and EPW are represented as generic
subprocess commands when their adapters provide command specifications.  BoltzTraP2
has a declared Python-API mode but no registered C6 binding, so it is not execution
ready.  NEGF remains `NOT_SELECTED`; C6 never substitutes a fake solver.  Shared QE
prefix/outdir and adapter-declared artifact locality remain adapter contracts; C6 does
not infer copy commands from filenames.

The Calculate workspace exposes an explicit generated-workflow directory selection,
preflight, asynchronous run, and cancellation control.  The selected request snapshot
and generated files remain authoritative while it runs.  Exit code zero means only
process-level success; convergence and scientific result parsing belong to C8.
Calculate prepares/runs/parses future Results, while Analyze remains the separate
visualization and interpretation workspace.
