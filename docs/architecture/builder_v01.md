# Quantum Studio v0.1 Builder architecture

## Package ownership

```text
frontend/
  app/                         Project Hub and ProjectWindow integration
  core/                        Project, Structure, Atom, and StructureIO
  builder/
    workspace.py               Builder workspace and StructureViewport
    view/                      View panel and crystallographic/view math
    measure/                   Measurement controller
    build/
      controller.py            Build-panel controller and dialogs
      operations.py            Widget-free structure-operation backend
      crystal/                 Crystal Builder dialog
      lattice_matching/        Shared public lattice-match API
      heterostructure/          Heterostructure public API
      moire/                    Moire public API
    brillouin_zone/            Brillouin-zone viewer
  calculate/                   Calculate workspace
```

The active application direction is:

```text
main -> app -> workspaces -> Builder feature controllers -> core
```

`core` never imports Qt or Builder modules. The canonical domain state is
`Project`, `Structure`, and `Atom`. Builder state (selection, camera,
projection, labels, visibility, background, and periodic display) belongs to
the workspace/viewport and is never serialized as structure data.

## ASE boundary

Build operations may use ASE internally. The only application-domain boundary
is `StructureIO.from_ase()` / `StructureIO.to_ase()` in `frontend.core`.
Builder controllers commit native `Structure` objects to `Project`; the
viewport renders native atoms. No renderer or feature package owns a second
canonical structure.

## Public APIs

Use package exports for new code:

- `frontend.core`: `Project`, `Structure`, `Atom`, `StructureIO`
- `frontend.builder`: `Builder`, `StructureViewport`
- `frontend.builder.build`: supported build operations and `BuilderBuildMixin`
- `frontend.builder.build.crystal`: `CrystalBuilderDialog`
- `frontend.builder.build.lattice_matching`: `LatticeMatch`,
  `find_best_2d_match`
- `frontend.builder.view`: reciprocal/Miller/fractional/MIC helpers
- `frontend.calculate`: `CalculateWorkspace`

Feature packages must not import another feature's underscore-prefixed helper.
Heterostructure and Moire use the shared lattice matching public boundary.

## Adding a Build feature

Create UI and validation with the build controller only when it is needed.
Place widget-free scientific work in `builder.build` and return ASE only at the
explicit interoperability boundary. Add a deliberate package export, then add
a matching focused test under `tests/builder/build/<feature>/`.

## Adding a viewer feature

Keep painting and camera behavior in `StructureViewport`; keep panel wiring in
`builder.view`. Viewer features may inspect native `Structure`, but may not
mutate it, Project history, or build operations. Add focused tests under
`tests/builder/view/`.

## Compatibility shims

Old module paths remain as re-export-only shims for v0.1 compatibility:
`frontend.project`, `frontend.structure`, `frontend.structure_io`,
`frontend.structure_operations`, `frontend.builder_view`,
`frontend.builder_build`, `frontend.builder_measure`, `frontend.builder_math`,
`frontend.crystal_builder`, `frontend.brillouin_zone`,
`frontend.project_hub`, `frontend.project_window`,
`frontend.calculate_workspace`, and the pre-existing Visualizer shims.

## Transitional debt

`builder.build.operations` intentionally retains the mature lattice matcher and
bilayer assembly in one widget-free module. Splitting that numerical code
further would change private helper placement and risks scientific regressions.
The public `lattice_matching` package isolates new consumers now; a later
version may mechanically relocate the matcher internals after adding an
independent numerical characterization suite.
