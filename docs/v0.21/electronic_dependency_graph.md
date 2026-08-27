# Quantum Studio v0.21 — Electronic Dependency Graph (E1)

This graph describes the active private-task architecture, not aspirational toolchains.

```text
SCF (pw.x)
 ├─→ GroundStateResult from pw.x stdout
 ├─→ Relax / VC-relax (pw.x) → RelaxationResult
 ├─→ Bands, semilocal: pw.x bands path → bands.x (`bands.dat`) → BandStructureResult
 ├─→ Bands, hybrid: hybrid SCF + ADDITIONAL_K_POINTS contract → bands.x → BandStructureResult
 ├─→ DOS: dense fixed-density NSCF (pw.x) → dos.x (`dos.dat`) → DOSResult
 ├─→ PDOS: dense fixed-density NSCF (pw.x) → projwfc.x (`pdos_atm#*`) → PDOSResult
 ├─→ Charge density: pp.x raw field → [no parser/result/viewer]
 ├─→ Spin density: spin SCF → pp.x raw field → [no parser/result/viewer]
 └─→ Wannierization: NSCF → wannier90 -pp + pw2wannier90 → wannier90 → WannierizationResult
```

The public `nscf` entry has no executable registry definition and remains `partial`. E1 defines its supported private role: a purpose-signed prerequisite with a deterministic parent SCF edge, the same immutable structure snapshot and scientific context, shared QE prefix/outdir/save state, workflow-local verified pseudopotentials, purpose-specific k-point settings, and required downstream artifacts. It intentionally produces no artificial standalone ScientificResult. A user-facing NSCF still requires an explicit eigenvalue/occupation artifact and result contract.

```text
Future work function (not implemented)
slab SCF → electrostatic/local potential → planar average → macroscopic average
         → defensible vacuum plateau + Fermi reference → WorkFunctionResult

Future charge-density difference (not implemented)
combined system field + component-A field + component-B field
→ aligned grids/cells and multi-system provenance → DifferenceFieldResult
```

Within one request the compiler creates a deterministic DAG and shares its private SCF prerequisite. It does not share prerequisites across independent requests/executions.
