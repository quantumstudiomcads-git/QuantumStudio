# B5.1 Terminology Standard

Use these terms consistently in B5.2. Internal identifiers may appear in
advanced/reference tables, but should not replace the public term in normal
instructional prose.

| Preferred public term | Meaning | Internal/source term | Avoid in user prose |
| --- | --- | --- | --- |
| Quantum Studio | The desktop product | `PRODUCT_NAME` | QuantumStudio, QS as a standalone product name |
| Project | A `.qs` project and its owned state | `Project` | document, workspace file |
| Project Hub | Start/open/recent-project window | `ProjectHub` | launcher dashboard |
| Builder | Structure construction and viewing workspace | `Builder` | Visualizer |
| Calculate | Calculation setup/execution workspace | `CalculateWorkspace` | calculator panel |
| Analyze | Result inspection/comparison workspace | `AnalyzeWorkspace` | post-processor |
| Device Builder | Entitlement-gated multi-region Device workspace | `DeviceBuilderWorkspace` | device visualizer |
| Structure | Canonical atomistic object | `frontend.core.Structure` | ASE structure as project storage |
| Atom | Canonical atom record | `frontend.core.Atom` | particle/site unless context requires |
| Calculation intent | Public catalogue item selected by user | catalogue `id` | engine command |
| Workflow | Compiled dependency-directed set of tasks | `ExecutionPlan`, generated workflow | a calculation, when precision matters |
| Engine | Scientific program/tool family | QE, Wannier90, EPW, BoltzTraP2 | workflow |
| Job / execution | One stored workflow attempt | `WorkflowExecutionRecord` | result |
| Result | Parsed, provenance-bearing scientific output | `ScientificResult` | raw output file |
| Pseudopotential | Validated species-specific input for QE | UPF/provenance record | a built-in atomic model |
| Unit cell | Lattice vectors plus periodicity | `Structure.cell` | box unless explaining display |
| Supercell | Explicit repeated structure | Builder operation | periodic display copy |
| Slab | Structure with surface/vacuum construction | Builder operation | 2D cell by default |
| Heterostructure | Matched multi-layer structure | Heterostructure builder | arbitrary stacked file |
| Moiré structure | Twist-preserving matched layered structure | Moiré builder | any rotated bilayer |
| Entitlement | Signed local policy decision | lease/policy | subscription proof when no server UI exists |
| Plan | Commercial policy label | `PlanId` | authorization implementation |

## Calculation acronyms

| Term | Preferred expansion/use | Notes |
| --- | --- | --- |
| SCF | Self-Consistent Field | Intent ID `scf` |
| NSCF | Non-Self-Consistent Field | Intent ID `nscf`; present in policy but current normal Calculate executability follows catalogue/registry support |
| Γ-point phonons | `phonons` | Direct phonon calculation at Γ; **not** phonon dispersion |
| Phonon DOS | `phonon_dos` | Density-of-states workflow |
| Phonon band structure | `phonon_band_structure` | q-path phonon dispersion workflow |
| PDOS | Projected Density of States | Do not call it simply DOS when projections matter |
| DFPT | Density-functional perturbation theory | Explain on first use |
| QE | Quantum ESPRESSO | Use full name first in a chapter |
| EPC | Electron–phonon coupling | Advanced/limited current workflow state |
| EPW | EPW tool/workflow | Not a bundled engine claim |
| SOC | Spin–orbit coupling | Use alongside spin-treatment context |
| BZ | Brillouin zone | Expand on first use |

## UI naming rules

- Use visible labels exactly in procedures: `New Project`, `Open Project`,
  `Export Diagnostics…`, `License Status`, `Compile`, `Generate QE Inputs`,
  `Run`, and `Results…`.
- Use **Build**, **View**, and **Measure** only for the actual Builder UI areas;
  do not call the whole workspace `Build`.
- Reciprocal-direction labels visible in the product may be `X*`, `Y*`, and
  `Z*`; describe their physical reciprocal-lattice meaning rather than
  substituting historical `a*`, `b*`, `c*` UI labels.
- Treat `Visualizer` and legacy `visualizer*` module names as compatibility
  history, not current manual vocabulary.

## Status language

| Term | Required meaning |
| --- | --- |
| PUBLIC | User-accessible now, subject to normal inputs and entitlement. |
| GATED | User-accessible only when an entitlement decision allows it. |
| IMPLEMENTED | Catalogued as ready with backend support. |
| PARTIAL | Public but incomplete/limited; executable only where the source explicitly permits it. |
| PLANNED | Discoverable intent, not executable. |
| INTERNAL | Implemented source capability not a public catalogue/UI feature. |
| FUTURE | Intentionally post-beta or otherwise not current. |
| VALID / PARTIAL / NOT_CONVERGED / UNVERIFIED / PARSE_FAILED / STALE | Scientific Result status, distinct from engine process completion. |
