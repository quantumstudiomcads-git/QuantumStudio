# Device Builder v0.1 architecture

## Device versus Structure

A `Device` is not a flattened `Structure`. It is an in-memory semantic assembly
containing ordered `DeviceRegion` objects. Every region retains its canonical
`frontend.core.Structure`; a flattened native `Structure` is derived only for
preview, export, or future calculation preparation.

## Region ownership and roles

A `DeviceRegion` owns a stable UUID, name, semantic `RegionRole`, source
Structure, translation, rotation, visibility, and metadata. Initial roles are
electrode, channel, active layer, substrate, dielectric, contact, gate,
adsorbate, interface, and other. Roles remain metadata only in v0.1.

## Transform convention

Quantum Studio uses row-vector Cartesian coordinates.

- Translation: `r_prime = r + t`
- Rotation about `r0`: `r_prime = (r - r0) @ R.T + r0`
- Rotation order: `R = Rz @ Ry @ Rx`

Translations are Å and rotations are degrees. Transform and assembly routines
return derived copies; they never mutate a region source Structure,
`Project.structure`, Builder history, or renderer state.

## Stage 2 placement and alignment

All geometry commands operate on the current transformed axis-aligned atomic
bounds of a moving region relative to an explicitly selected reference region.
The source Structure is never edited.

- **Above:** `zmin(moving) = zmax(reference) + gap`
- **Below:** `zmax(moving) = zmin(reference) - gap`
- **Right:** `xmin(moving) = xmax(reference) + gap`
- **Left:** `xmax(moving) = xmin(reference) - gap`

The UI defaults the bounding-plane gap to 3.0 Å. Center alignment supports X,
Y, Z, XY, and XYZ. Surface alignment supports equal named top, bottom, left,
and right bounding planes. Reference and moving regions must be distinct.

## Repetition

`repeat_region` creates independent `DeviceRegion` copies for the requested
`Nx × Ny × Nz` range, preserving the original at `(0, 0, 0)`. New copies have
fresh IDs and their placement uses the selected region's *currently oriented*
row-vector cell:

`translation = i*a + j*b + k*c`

The transform rotation is therefore respected. Repetition is bounded to counts
1 through 10 and requires a finite nonsingular source cell. It is not Builder's
Supercell operation and never changes the source Structure.

## Device cell, padding, and origin policy

The Device cell is independent of all region cells. **Fit Cell to Device**
constructs an axis-aligned 3×3 Cartesian cell enclosing all visible transformed
atoms with the selected non-negative X/Y/Z padding. Z padding is labelled
vacuum in the UI but has no slab-specific semantics.

Fitting sets a Device-level `origin_offset`, applied only while assembling. This
moves the complete derived geometry inside the fitted cell while preserving all
relative region transforms and positions. No source Structure is strained or
translated. Device PBC are preserved exactly; they are never inferred by the
fit operation.

## Collision diagnostics

`detect_inter_region_collisions` checks direct Cartesian distances only between
atoms in different visible regions. A contact is reported when:

`distance < 0.75 * (covalent_radius_i + covalent_radius_j)`

ASE covalent radii supply the radii. Each `DeviceCollision` stores both region
IDs, source-local atom indexes, distance, and threshold. These are warnings,
not assembly blockers. Periodic minimum-image collision detection is deferred;
Stage 2 intentionally does not introduce another MIC implementation.

## Assembly and membership

`assemble_device(device)`:

1. takes visible DeviceRegions in Device order;
2. obtains transformed source copies;
3. applies the Device-level origin offset;
4. combines native Atom copies;
5. applies explicit Device cell/PBC, or a non-periodic derived preview cell;
6. returns `DeviceAssembly`.

`DeviceAssembly.atom_region_ids` records one region UUID per flattened atom.
This avoids modifying the frozen Atom/Structure schema or reconstructing
membership from fragile index ranges.

## Dependency direction and preview

    Device Builder UI -> Device Builder assembly -> Device Builder model -> core
    Device Builder UI -> existing StructureViewport

Model and assembly modules are widget-free. The workspace passes only the
derived native Structure to the existing Builder `StructureViewport`; the
viewport has no DeviceRegion semantics.

**Add Current Builder Structure** uses the public `Project.get_structure()`
boundary, makes an independent copy for the DeviceRegion, and never reads a
Builder widget/private field.

## Project ownership and persistence

`Project` is the sole persistent owner of the active Device. New projects start
with `Project.device is None`; Device Builder presents a lazy empty Device until
the first committed Device edit. At that point it calls `Project.set_device()`
and the regular Project dirty flag is updated.

`.qs` format v0.3 adds an **optional** `device` section. The existing
structure/calculator/workflow fields are unchanged. A pre-Device v0.2 project
without this section loads normally with `Project.device is None`.

The Device section serializes canonical source state only:

- Device: id, name, regions, explicit cell or `null`, PBC, transport direction,
  padding, origin offset, and metadata;
- DeviceRegion: id, name, role, source Structure through `Structure.to_dict()`,
  translation, rotation, visibility, and metadata.

Assembled preview atoms, transformed source copies, bounds, collision results,
viewport state, selection/reference widgets, dialogs, and history are excluded.
They are derived again after load. Device and region UUIDs are supplied back to
the model during deserialization and are never regenerated.

`Project.load()` validates a present Device widget-free. Malformed optional
Device data leaves the remainder of the Project available, sets
`Project.device` to `None`, and exposes `Project.device_load_error` for the
Device Builder workspace to report.

## Device history

Device Builder has a Qt-free `DeviceHistory` that is independent of Builder's
Structure history. v0.1 uses complete before/after Device serialization
snapshots per committed command. This is deliberately conservative: it makes
add/remove/duplicate, property edits, placement/alignment, repetition, padding,
and cell fitting deterministic and reversible without modifying source
Structures.

The public workspace API is `can_undo()`, `can_redo()`, `undo()`, `redo()`, and
`clear_history()`. History is never serialized. Loading a project restores the
Device model and begins with empty Device undo/redo stacks.

Undo/redo controls live in Device Builder. ProjectWindow routes its existing
Ctrl+Z, Ctrl+Shift+Z, and Ctrl+Y actions to Device Builder only while that
workspace is active; Builder operations continue to use the frozen Builder
history when Builder is active.

## Device interfaces and shared matching

A `DeviceInterface` is a persistent semantic relationship between exactly two
DeviceRegions. It stores stable interface/region IDs, aligned or twisted mode,
requested twist, max strain, existing Builder strain mode, gap, max index, and
serializable scientific diagnostics. It has no transport behavior.

Device Builder does **not** implement a matcher. Its interface service calls
only the frozen public Builder APIs:

- `frontend.builder.build.heterostructure.create_heterostructure` for aligned
  Z-stacked interfaces;
- `frontend.builder.build.moire.create_moire_structure` for twisted interfaces.

Those APIs remain the source of truth for HNF matching, Cartesian residuals,
polar-decomposition strains, common-target construction, strict Moiré rotation
preservation, and atomic assembly. The ordered A/B result is split using the
recorded determinant-derived atom counts and converted through `StructureIO`.

## Interface source-replacement policy

Normal placement remains non-destructive. **Match Interface** is an explicit,
reversible geometry-generation command: it replaces the two participating
Region source Structures with their matched/deformed A and B supercells and
resets only those regions' Device transforms to zero. Their stable Region IDs,
roles, visibility, and metadata remain unchanged. The replacement sources
already contain the accepted common lattice, requested physical twist (once),
and outermost-plane Z gap.

This currently supports only Z-stacked interfaces, matching the frozen Builder
Heterostructure/Moiré semantics. Stage 2 geometric left/right placement remains
separate; arbitrary crystallographic X/Y interfaces are not claimed.

An interface match is one Device history snapshot. Undo restores both original
source structures, transforms, interface list, cell/origin state, and redo
restores the matched state deterministically. Removing a participating Region
cleans up its interfaces; duplicating a Region creates no interface links.

## Interface safety and UI responsiveness

Interface input validates distinct regions, native source structures, planar
cells through the shared Builder APIs, finite twist/strain/gap, and positive
max index. A conservative 100,000 atom hard cap rejects excessive searches.
The UI shows determinants, atom count, principal strain, residual rotation,
Cartesian residual, requested twist, and gap after a successful match.

The UI runs matching in a short-lived `QThread` worker. The worker only computes
an `InterfaceMatchResult`; it never mutates Device or widgets. The main thread
commits the one history command. The frozen matcher is bounded but not
cancellable during an individual call, so the UI disables Match while a worker
is active.

Interfaces are serialized as an optional `Device.interfaces` list inside the
existing v0.3 optional Device section. Existing v0.3 Device records without
`interfaces` deserialize as an empty list. Candidate caches, worker state, and
history remain non-persistent.

## Deferred work

Still deferred: periodic collision checks, interface candidate browsing or
cancellation, arbitrary non-Z interface orientation, Heterostructure/Moiré
templates, collision visualization, electrodes, gates, NEGF, transport physics,
and Device-specific command coalescing beyond widget `editingFinished` commits.
