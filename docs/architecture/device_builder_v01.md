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

## Persistence and deferred work

Device state remains in memory only. `.qs` serialization is intentionally
unchanged. A dedicated persistence stage must serialize Device identity,
regions/source structures, transforms, roles, cell, PBC, transport direction,
padding, origin offset, and metadata while retaining old-project compatibility.

Still deferred: Device undo/redo, periodic collision checks, lattice/interface
matching, Heterostructure/Moiré integration, automatic placement beyond the
Stage 2 geometric operations, collision visualization, templates, electrodes,
gates, NEGF, and transport physics.
