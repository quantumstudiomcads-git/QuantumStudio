# Quantum Studio — AGENTS.md

This file defines repository-wide development rules for AI coding agents working on Quantum Studio.

These instructions apply to the entire repository unless a more specific `AGENTS.md` exists inside a subdirectory.

---

# 1. PROJECT IDENTITY

Project name:

Quantum Studio

Project file extension:

.qs

Quantum Studio is a PySide6 desktop application for:

- atomistic structure construction;
- crystal visualization;
- device construction;
- simulation workflow preparation;
- later analysis.

Primary technologies:

- Python
- PySide6
- ASE at interoperability/computational boundaries
- native Quantum Studio `Structure` / `Atom`
- custom QPainter-based rendering

Do not abbreviate Quantum Studio in user-facing application text.

---

# 2. GIT / RELEASE STATE

The Builder v0.1 baseline is frozen.

Frozen tag:

v0.1-builder-freeze

The Device Builder is developed separately.

Before making changes, always inspect:

    git status
    git branch --show-current

Do not modify, move, rewrite, or retag:

    v0.1-builder-freeze

Use feature branches for major work.

Do not use destructive Git operations without explicit authorization.

Avoid:

    git reset --hard
    git clean -fd
    git push --force

Git is the source-history system.

Do not create ad-hoc source backups such as:

    file.py.old
    file.py.backup
    file.py.before_fix
    file.py.broken

---

# 3. PRIMARY ARCHITECTURAL PRINCIPLE

Quantum Studio uses feature-owned modular architecture.

The primary design goals are:

- high cohesion;
- low coupling;
- explicit public interfaces;
- predictable dependency direction;
- isolated feature implementation;
- minimal cross-feature side effects.

Changing one feature should not require unrelated features to know about its internal implementation.

Prefer:

    small explicit compatible extension

over:

    broad redesign

Do not perform unrelated cleanup while implementing a feature.

---

# 4. HIGH-LEVEL ARCHITECTURE

The active frontend architecture is approximately:

frontend/
    app/
    core/
    builder/
    device_builder/
    calculate/
    analyze/

Responsibilities are intentionally separated.

---

# 5. frontend/app

`frontend/app` owns application-level orchestration.

Examples:

- Project Hub;
- ProjectWindow;
- workspace navigation;
- recent projects;
- top-level workspace construction.

Current major workspaces are conceptually:

    Builder
    Device Builder
    Calculate
    Analyze

ProjectWindow may construct and coordinate workspaces.

ProjectWindow must not contain:

- lattice-matching algorithms;
- geometry operations;
- device assembly algorithms;
- renderer internals;
- scientific calculation logic.

Keep application-shell logic thin.

---

# 6. frontend/core

`frontend/core` is the canonical domain layer.

Public domain types include:

    Project
    Structure
    Atom
    StructureIO

Core should remain independent of Qt widgets whenever practical.

Core must not depend on:

- Builder UI;
- Device Builder UI;
- StructureViewport;
- dialogs;
- toolbar actions.

The preferred dependency direction is downward toward core, never from core into feature UI.

---

# 7. CANONICAL STRUCTURE CONTRACT

The canonical UI-facing and persistent atomistic representation is:

    frontend.core.Structure
    frontend.core.Atom

ASE `Atoms` is an interoperability/computational representation only.

Preferred flow:

    native Structure
        ↓
    StructureIO.to_ase()
        ↓
    ASE operation
        ↓
    StructureIO.from_ase()
        ↓
    native Structure

Do not leave ASE `Atoms` stored where native `Structure` is expected.

Do not directly assign ASE `Atoms` to canonical project/application structure state unless an explicit public API requires it.

---

# 8. BUILDER STATUS

The Builder v0.1 subsystem is feature-frozen.

Builder currently owns:

- structure import;
- Crystal Builder;
- Supercell;
- Slab;
- Vacuum;
- Strain;
- Nanotube;
- Layered Structure;
- Heterostructure;
- Moiré;
- structure viewing;
- crystallographic views;
- selection;
- measurement;
- periodic display;
- background control;
- screenshot/export;
- Brillouin-zone visualization.

Do not refactor frozen Builder code during unrelated Device Builder work.

Any modification to Builder requires:

1. a specific reason;
2. focused regression tests;
3. confirmation that frozen behavior is preserved.

---

# 9. BUILDER PACKAGE STRUCTURE

The modular Builder architecture is approximately:

frontend/builder/
    workspace.py

    view/
        panel.py
        math.py

    measure/
        controller.py

    build/
        controller.py
        operations.py

        crystal/
        lattice_matching/
        heterostructure/
        moire/

    brillouin_zone/
        viewer.py

This tree may evolve, but ownership boundaries must remain clear.

Do not collapse these features back into one large Builder implementation.

---

# 10. RENDERER IS FROZEN

Quantum Studio uses the existing custom QPainter renderer.

Primary renderer-facing component:

    StructureViewport

Do not replace it with:

- PyVista;
- VTK;
- another OpenGL engine;
- another 3D rendering framework.

Device Builder must also reuse StructureViewport rather than creating a second renderer.

Existing renderer behavior must remain stable:

- atoms;
- bonds;
- unit cell;
- axes;
- rotation;
- pan;
- zoom;
- picking;
- selection;
- measurements;
- projection;
- display controls;
- background;
- screenshot/export.

---

# 11. BUILDER NAMING

The atomistic workspace is called:

    Builder

not:

    Visualizer

`StructureViewport` remains the rendering widget name.

Legacy `visualizer*` modules may exist only as thin compatibility re-export shims.

Do not place new implementation code in legacy Visualizer modules.

---

# 12. BUILDER IMPORT LOCATION

There is one user-facing structure import path:

    Builder
        → Build
        → Import Structure

Do not add Import Structure back to the top toolbar.

---

# 13. BUILDER TOOLBAR CONVENTION

The Builder top toolbar is intended to behave like a compact scientific structure viewer.

Current high-frequency controls conceptually include:

    Undo
    Redo
    Reset

    X
    Y
    Z

    X*
    Y*
    Z*
    (hkl)

    Perspective / Orthographic

    Bonds
    Cell
    Labels
    Species

    Select
    Center
    Measure

    Periodic display
    Background
    Export
    Fullscreen

Do not reintroduce redundant a/b/c viewer controls.

---

# 14. RECIPROCAL-SPACE CONVENTION

For direct lattice row vectors:

    a
    b
    c

with:

    V = a · (b × c)

use:

    a* = 2π (b × c) / V
    b* = 2π (c × a) / V
    c* = 2π (a × b) / V

UI labels may appear as:

    X*
    Y*
    Z*

but the implementation must use the actual reciprocal lattice.

Do not replace reciprocal directions with simple Cartesian unit vectors.

For Miller-plane view:

    G_hkl = h a* + k b* + l c*

Reject:

    (0, 0, 0)

---

# 15. ROW-VECTOR GEOMETRY CONVENTION

Quantum Studio uses row-vector geometry.

Fractional coordinates:

    r_cart = r_frac @ cell

therefore:

    r_frac = r_cart @ inverse(cell)

Deformation convention:

    target = source @ F.T

therefore:

    F = (inverse(source) @ target).T

Rigid rotation around r0:

    r' = (r - r0) @ R.T + r0

Device-region transformation additionally includes translation.

Do not alter transpose conventions casually.

Any change touching coordinate mathematics requires focused numerical tests.

---

# 16. HETEROSTRUCTURE / MOIRÉ MATCHER

The shared lattice matcher is scientifically sensitive.

Public boundary:

    frontend.builder.build.lattice_matching

It is shared by Heterostructure and Moiré.

Current strategy includes:

- canonical row-HNF enumeration;
- determinant-bounded search;
- nearest-integer local inference;
- bidirectional search;
- exact integer determinants;
- cached candidate geometry;
- cheap geometric prefilters;
- Cartesian orientation-sensitive residual;
- polar decomposition;
- principal strain diagnostics;
- residual rotation;
- deterministic ranking;
- identity fast path.

Do not restore brute-force HNF-A × HNF-B Cartesian products.

Do not alter matcher mathematics as part of unrelated work.

---

# 17. HETEROSTRUCTURE

Heterostructure is frozen for Builder v0.1.

It currently supports:

- shared lattice matching;
- balanced strain;
- deform-bottom;
- deform-top;
- interlayer distance;
- vacuum;
- layered PBC;
- metadata;
- native Structure handoff.

Modify only when a reproducible bug or explicit task requires it.

---

# 18. MOIRÉ

Moiré is frozen for Builder v0.1.

Key physical constraint:

    requested twist must be preserved

The matching condition is based on:

    MA @ A ≈ MB @ B_theta

where:

    B_theta = B @ R(theta).T

The requested twist is physically applied exactly once.

Known validation case:

    theta = acos(13/14)
          ≈ 21.786789 degrees

for identical hexagonal lattices, producing determinant-7 commensurate cells.

Do not break this validation.

---

# 19. DEVICE BUILDER STATUS

Device Builder Stage 1 is implemented.

It is a sibling workspace to Builder.

Current Device Builder capabilities include:

- Device model;
- DeviceRegion model;
- semantic region roles;
- add region from structure file;
- remove region;
- duplicate region;
- rename region;
- show/hide region;
- region translation;
- region rotation;
- Device assembly;
- native Structure preview;
- Device cell;
- Device PBC;
- transport-direction metadata;
- validation;
- Device Builder workspace UI;
- StructureViewport preview.

The frozen Builder implementation was not changed for Stage 1.

---

# 20. DEVICE BUILDER PACKAGE

Current package is approximately:

frontend/device_builder/
    model/
        device.py
        region.py

    assembly/
        assembler.py
        validation.py
        transforms.py      # if present

    ui/
        ...

    workspace.py

Use the actual repository tree as the source of truth.

Do not create architecture purely to match this document.

Feature ownership matters more than cosmetic symmetry.

---

# 21. DEVICE IS NOT A STRUCTURE

This is a fundamental rule.

A Device is a semantic object containing multiple DeviceRegions.

Conceptually:

    Device
        ├── Region
        ├── Region
        ├── Region
        └── ...

Do not replace Device with one flattened atom list.

Flattened/assembled Structure is a derived output used for:

- preview;
- export;
- calculations;
- geometry inspection.

Region identity must remain preserved at the Device level.

---

# 22. DEVICE MODEL

Device owns device-level state such as:

- ID;
- name;
- regions;
- Device cell;
- PBC;
- transport direction;
- metadata.

Device is a domain object.

Device must not depend on:

- QWidget;
- QMessageBox;
- StructureViewport;
- toolbar actions;
- dialogs.

Device model imports must remain Qt-free.

---

# 23. DEVICE REGION MODEL

A DeviceRegion owns or references:

- unique region ID;
- name;
- semantic role;
- source Structure;
- translation;
- rotation;
- visibility;
- metadata.

Source Structure and device placement are separate concepts.

DeviceRegion transforms must be non-destructive.

Do not modify the source Structure simply because a region moves in Device Builder.

---

# 24. DEVICE TRANSFORMATION CONVENTION

Device Builder Stage 1 uses:

    R = Rz @ Ry @ Rx

with row-vector application:

    r' = (r - r0) @ R.T + r0 + translation

The rotation order is part of the current contract.

Do not silently change it.

Translation units:

    Å

Rotation units:

    degrees

Do not add scaling or strain unless explicitly requested.

---

# 25. SOURCE STRUCTURE IMMUTABILITY

Calling a transformation/assembly operation on a DeviceRegion must not mutate:

    region.source_structure

or:

    Project.structure

Device transformations belong to Device state.

The derived transformed Structure is disposable/recomputable.

Keep tests proving this behavior.

---

# 26. DEVICE ASSEMBLY

Current architecture:

    Device
        ↓
    visible DeviceRegions
        ↓
    derive transformed copies
        ↓
    combine atoms
        ↓
    apply Device cell / PBC
        ↓
    native Structure

The public assembled result should remain:

    frontend.core.Structure

Do not make ASE the public Device assembly representation.

---

# 27. REGION MEMBERSHIP

Assembly returns/maintains a separate atom-to-region ID mapping.

This is deliberate.

Do not infer region membership later from fragile atom-index ranges.

Do not modify the canonical Atom/Structure schema merely to store DeviceRegion identity unless an explicit schema decision is made later.

Preserve semantic region identity at Device level.

---

# 28. DEVICE CELL AND PBC

Device cell is distinct from individual region/source cells.

When an explicit Device cell is defined:

- propagate it unchanged to assembled preview/output;
- propagate Device PBC unchanged.

If no Device cell is defined, Stage 1 may derive a safe non-periodic preview cell.

Do not silently strain regions to fit the Device cell.

Device-cell fitting is a later placement capability.

---

# 29. TRANSPORT DIRECTION

Device currently stores semantic transport direction.

Initial directions:

    X
    Y
    Z

Transport direction is metadata only at this stage.

It must not:

- move atoms;
- rotate structures;
- invoke transport physics;
- imply NEGF automatically.

---

# 30. DEVICE REGION ROLES

Initial semantic roles include:

    ELECTRODE
    CHANNEL
    ACTIVE_LAYER
    SUBSTRATE
    DIELECTRIC
    CONTACT
    GATE
    ADSORBATE
    INTERFACE
    OTHER

Roles are semantic metadata.

Do not attach calculation physics automatically to a role unless explicitly implemented in a future stage.

---

# 31. DEVICE VALIDATION

Device validation must remain widget-free.

Validation should cover at least:

- valid Device;
- unique region IDs;
- valid Structures;
- finite transforms;
- valid cell when supplied;
- three-component PBC;
- valid transport direction;
- finite assembled coordinates.

Scientific/domain validation must not invoke QMessageBox.

UI may translate validation results into user-facing feedback.

---

# 32. DEVICE PREVIEW

Device Builder preview reuses:

    StructureViewport

The architecture is:

    Device
        ↓
    assembler
        ↓
    native Structure
        ↓
    StructureViewport

StructureViewport must not be modified to understand DeviceRegion objects.

Do not create a Device-specific renderer.

---

# 33. DEVICE BUILDER WORKSPACE

Device Builder is a major sibling workspace.

It should not be implemented as another Builder tab.

Conceptually:

    Builder
    Device Builder
    Calculate
    Analyze

Stage 1 workspace currently supports:

- region list/tree;
- Add Region;
- Remove Region;
- Duplicate Region;
- Rename;
- Role;
- Visibility;
- Translation;
- Rotation;
- Device preview.

Preserve this separation.

---

# 34. DEVICE PERSISTENCE AND HISTORY POLICY

Device state is persisted optionally in `.qs` format v0.3 through the public
`Project.device` boundary. Existing projects without a `device` section remain
valid and load with `Project.device is None`.

Persist canonical Device/DeviceRegion source state only: stable IDs, roles,
source Structures, transforms, visibility, metadata, Device cell/PBC,
transport direction, padding, origin offset, and semantic DeviceInterfaces.
Do not persist assembled
previews, viewport state, bounds, collision caches, selections, or history.

Malformed optional Device data must not prevent the remainder of a Project from
loading. Expose a clear recoverable Device load error instead.

Device undo/redo is session-only and separate from frozen Builder Structure
history. It must never be serialized into `.qs` files or coupled to Builder's
history stack.

Do not make further breaking `.qs` changes casually.

---

# 35. ADD CURRENT BUILDER STRUCTURE

Stage 1 does not yet implement:

    Add Current Builder Structure

Do not reach through Builder private widgets to implement it.

When added, use a clean public application/project interface.

Avoid:

    parent().parent().builder.some_private_field

Prefer:

- Project-level public state;
- explicit signals;
- controller methods;
- application orchestration.

---

# 36. DEVICE UNDO / REDO

Device Builder has session-only snapshot-based DeviceHistory. It is independent
of frozen Builder atomistic history and is routed by active workspace. Device
commands, including explicit interface matching, must use this history as one
meaningful reversible action.

Do not couple the two histories or serialize Device history into `.qs` files.

---

# 37. DEVICE BUILDER DEVELOPMENT ROADMAP

Current planned progression:

## Stage 1 — Foundation

COMPLETE.

Includes:

- Device;
- DeviceRegion;
- roles;
- transforms;
- assembly;
- preview;
- basic region UI.

## Stage 2 — Placement and geometry management

Planned:

- Add Current Builder Structure;
- Place Above;
- Place Below;
- Place Left;
- Place Right;
- Align Centers;
- Align Surfaces;
- Set Gap;
- Repeat Region;
- Fit Device Cell;
- padding;
- vacuum;
- collision detection;
- possibly Device `.qs` persistence if architecture is ready.

## Stage 3 — Interface integration

COMPLETE.

Uses frozen public Heterostructure/Moiré APIs for aligned and twisted Z-stacked
interfaces. DeviceInterface retains semantic links and diagnostics; matching is
an explicit reversible source-structure replacement operation.

## Stage 4 — Device templates

COMPLETE.

`frontend.device_builder.templates` owns a Qt-free `DeviceTemplate` contract
and deterministic registry. Templates build complete replacement Devices
transactionally, compose existing Device Builder primitives, and commit as one
DeviceHistory command from the workspace. Do not add template-specific geometry
algorithms to workspace UI code.

Initial templates are:

- Vertical Stack (optionally through the public Stage 3 interface path);
- Lateral Two-Probe;
- Tunnel Junction;
- Surface + Adsorbate.

These are geometry/semantic-role constructors only. They do not imply NEGF,
principal layers, valid transport leads, calculations, relaxation, or automated
adsorption-site discovery.

---

# 38. FUTURE DEVICE PLACEMENT PRINCIPLE

Manual XYZ translation is not enough for a scientific Device Builder.

Semantic operations should eventually include:

    Place Above
    Place Below
    Place Left
    Place Right
    Align Centers
    Align Surfaces
    Set Gap

These operations should update DeviceRegion transforms, not destructively rewrite source Structure geometry.

---

# 39. DEVICE INTERFACE MATCHING

Device Builder must not implement a second lattice-matching engine. Stage 3
interfaces reuse frozen public Builder Heterostructure/Moiré APIs, which in turn
use the validated shared lattice matcher. Do not duplicate or alter matcher
mathematics during Device work.

Interface matching is explicit and may replace the two participating Region
source Structures with matched supercells. Preserve Region IDs and make the
operation one reversible Device history command.

---

# 40. VIEW STATE VS DOMAIN STATE

Keep these categories distinct.

DOMAIN STATE:

    Project
    Structure
    Atom
    Device
    DeviceRegion

VIEW STATE:

    camera
    projection
    labels
    background
    visible species
    selected atom
    periodic display copies
    current viewport center

DEVICE PLACEMENT STATE:

    region translation
    region rotation
    region visibility
    device cell
    device PBC

Do not mix these categories accidentally.

---

# 41. PERIODIC DISPLAY COPIES

Builder periodic images are visualization-only.

They are NOT atomistic Supercells.

Do not increase canonical atom count for periodic display.

Current periodic copies may remain non-selectable.

Preserve this safe behavior unless explicitly extending picking.

---

# 42. MINIMUM-IMAGE CONVENTION

For displacement:

    Δr = r_j - r_i

fractional displacement:

    Δs = Δr @ inverse(cell)

For each periodic component:

    Δs_k = Δs_k - round(Δs_k)

then:

    Δr_MIC = Δs @ cell

and:

    d_MIC = ||Δr_MIC||

Respect each PBC direction separately.

Do not wrap non-periodic dimensions.

---

# 43. FEATURE OWNERSHIP

Prefer feature-specific modules/packages.

Good examples:

    builder/build/heterostructure/
    builder/build/moire/
    builder/view/
    builder/measure/

    device_builder/model/
    device_builder/assembly/
    device_builder/ui/

Avoid broad generic modules such as:

    misc.py
    random_helpers.py
    everything_utils.py

Do not create one directory for every button.

A package should represent a coherent feature/domain.

---

# 44. PUBLIC API BOUNDARIES

Import through public package boundaries where available.

Preferred:

    from frontend.core import Structure
    from frontend.builder import Builder, StructureViewport
    from frontend.builder.build.lattice_matching import ...
    from frontend.device_builder.model import ...

Avoid importing another feature's `_private_helper`.

If two features require the same private logic, determine whether that logic belongs in a shared public package.

Do not duplicate scientific algorithms.

---

# 45. COMPATIBILITY SHIMS

Legacy modules remain as thin compatibility re-export shims.

Examples include older:

- project;
- structure;
- structure_io;
- Builder mixin paths;
- Visualizer paths;
- ProjectWindow paths;
- Calculate paths.

Rules:

- one active implementation only;
- shims contain no copied logic;
- new code uses modular paths;
- do not expand legacy compatibility modules;
- do not delete them casually.

---

# 46. SIGNALS AND UI COMMUNICATION

Prefer:

- explicit public methods;
- Qt signals;
- controllers;
- application orchestration.

Avoid fragile widget traversal:

    parent().parent().parent().something

Do not let Device Builder manipulate Builder private widgets.

Do not let one feature directly mutate another feature's UI internals.

---

# 47. SCIENTIFIC CODE POLICY

For scientific geometry and lattice code:

- document equations;
- state coordinate conventions;
- test non-orthogonal cells;
- test invalid/singular cases;
- preserve deterministic behavior;
- avoid magic transformations;
- reject impossible geometry clearly;
- do not force an unphysical result merely to satisfy the UI.

Numerical behavior is part of the feature contract.

---

# 48. ERROR HANDLING

Domain/scientific code should return or raise meaningful failures.

Avoid:

    except Exception:
        pass

unless there is an explicitly documented reason.

Do not use GUI dialogs inside domain/scientific code.

UI code may convert domain errors into QMessageBox or inline feedback.

---

# 49. PERFORMANCE

First fix pathological algorithms.

Do not use threading as a substitute for algorithmic correctness.

Known example:

large Heterostructure/Moiré searches such as high max_index values may take seconds.

If a scientifically bounded operation is still slow, use proper worker/progress/cancellation infrastructure rather than freezing the Qt event loop.

Do not introduce concurrency casually into numerical code.

---

# 50. TEST POLICY

Before substantial changes:

1. identify relevant tests;
2. record baseline;
3. make the smallest safe change;
4. run focused tests;
5. run full relevant suite;
6. run import smoke;
7. launch application when UI is affected.

Current post-Device-Stage-1 baseline:

    50 tests passing

This number may increase.

Do not treat exactly 50 as the permanent success criterion.

The requirement is:

    all currently relevant previously passing tests remain passing.

Stage 1 Device-specific baseline:

    8 Device tests passing

---

# 51. GUI VERIFICATION POLICY

Do not claim full GUI/manual verification from:

- import smoke;
- offscreen Qt test;
- startup timeout.

Report accurately whether verification was:

- unit test;
- offscreen Qt test;
- launcher startup;
- real click-through manual GUI verification.

Manual interaction may still be required for final feature freeze.

---

# 52. CALCULATE / BACKEND SCOPE

Do not fix unrelated calculation/compiler/backend issues during Builder or Device Builder work unless explicitly requested.

Keep task scope narrow.

Builder and Device Builder development must not destabilize calculation APIs.

---

# 53. FILE CREATION STYLE

Create modules only where a real responsibility boundary exists.

Do not generate dozens of one-function files merely to make the directory tree look modular.

Avoid giant god modules when responsibilities can be separated safely.

Prefer clarity over artificial symmetry.

---

# 54. CODE CHANGE STYLE

Prefer minimal compatible edits.

Do not rewrite working files wholesale without necessity.

Preserve public signatures where practical.

If a public API changes:

- update all callers;
- update tests;
- document the change.

Do not alter scientific behavior during unrelated UI refactors.

---

# 55. TEST / SOURCE ORGANIZATION

Tests should mirror feature ownership where practical.

Examples:

tests/
    builder/
        build/
        view/

    device_builder/

Integration tests should cover cross-feature contracts without exposing internal implementation details.

---

# 56. DOCUMENTATION

Current architecture documentation includes:

    docs/architecture/builder_v01.md
    docs/architecture/device_builder_v01.md

When architecture changes materially, update the appropriate developer documentation.

Do not let docs describe speculative architecture after implementation diverges.

---

# 57. IMPLEMENTATION REPORTING

After substantial tasks, report:

A. Files added
B. Files modified
C. Files modified outside the intended feature
D. Public API changes
E. Architecture/dependency changes
F. Geometry/scientific conventions affected
G. Tests run
H. Test results
I. Import/startup results
J. Manual GUI verification status
K. Known limitations
L. Deferred work

Do not hide partial failures.

---

# 58. DEFINITION OF DONE

A feature is normally complete only after:

    implementation
    +
    focused tests
    +
    regressions
    +
    import validation
    +
    application startup
    +
    appropriate GUI verification
    +
    documented limitations

Scientific features additionally require numerical validation.

---

# 59. CURRENT PRIORITY

Current active development priority is:

    Device Builder v0.1

Stage 1 foundation is complete.

The next intended development stage is:

    Device Builder Stage 2 — Placement and geometry management

Builder v0.1 must remain stable during this work.

---

# 60. FINAL RULE

When uncertain between:

    modifying existing frozen functionality

and:

    adding a small explicit public integration boundary

prefer the explicit integration boundary.

Quantum Studio should grow through stable interfaces rather than repeated rewrites.
