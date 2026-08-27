# Quantum Studio v0.21 — Electronic Dependency Graph (E2)

This graph describes the active private-task architecture, not aspirational toolchains.

```text
SCF (pw.x)
 ├─→ GroundStateResult from pw.x stdout
 ├─→ Relax / VC-relax (pw.x) → RelaxationResult
 ├─→ Bands, semilocal: pw.x bands path → bands.x (`bands.dat`) → BandStructureResult
 ├─→ Bands, hybrid: hybrid SCF + ADDITIONAL_K_POINTS contract → bands.x → BandStructureResult
 ├─→ DOS: purpose-signed dense fixed-density DOS NSCF (pw.x) → dos.x (dos.dat, raw eV plus optional EFermi/integrated DOS) → DOSResult
 ├─→ PDOS: purpose-signed dense fixed-density PDOS NSCF (pw.x) → projwfc.x (bounded prefixed pdos_atm files) → PDOSResult
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


## E2 DOS/PDOS Result boundary

DOSResult preserves the raw engine energy array in eV, total DOS, optional integrated DOS, optional QE EFermi, PER_CELL normalization metadata, source hashes, and task lineage. Fermi provenance is deterministic: a dos.x header wins; otherwise only the parent SCF GroundStateResult may supply it. PDOS uses that same parent-SCF fallback and never searches an unrelated sibling or prior workflow. Analyze derives E minus EF only as a display axis. PDOSResult preserves original component arrays plus deterministic atom/species/orbital identities and validates a common energy grid before aggregation; it never normalizes its sum to total DOS. E2 intentionally supports scalar/non-spin DOS and PDOS semantics only. Collinear-spin column contracts and SOC/noncollinear spinor projection semantics remain E3 work.
