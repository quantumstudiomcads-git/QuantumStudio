# Device Builder v0.1 Stage 1 architecture

## Device versus Structure

A Device is not a flattened Structure. It is an in-memory assembly model
containing semantic DeviceRegion objects. Each region retains a canonical
source frontend.core.Structure; the flattened native Structure is derived
only for preview or later computation.

## Region ownership and roles

A DeviceRegion owns:

- stable UUID identity
- name and semantic RegionRole
- source Structure
- independent translation and rotation
- visibility and metadata

Initial roles are electrode, channel, active layer, substrate, dielectric,
contact, gate, adsorbate, interface, and other. They are metadata only; no
calculation behavior is attached in Stage 1.

## Transform convention

Coordinates follow Quantum Studio row-vector conventions.

- Translation: r_prime = r + t
- Rotation about reference point r0:
  r_prime = (r - r0) @ R.T + r0
- Rotation order: R = Rz @ Ry @ Rx

Transforms return a copied Structure and never mutate the region source
Structure, Project.structure, Builder history, or renderer state.

## Assembly

assemble_device(device):

1. considers visible regions in Device order;
2. obtains a transformed source copy for each;
3. combines native Atom copies;
4. applies explicit Device cell/PBC, or a non-periodic derived preview cell;
5. returns DeviceAssembly.

DeviceAssembly.atom_region_ids records one region UUID per flattened atom.
This avoids changing the frozen Atom/Structure schema or relying on external
index ranges.

## Dependency direction

    Device Builder UI -> Device Builder assembly -> Device Builder model -> core
    Device Builder UI -> existing StructureViewport

The model and assembly are widget-free. Importing
frontend.device_builder.model does not import PySide6 or Builder UI.

## Preview

The Device Builder workspace derives a native Structure and passes it directly
to the existing Builder StructureViewport. The viewport has no knowledge of
Device or DeviceRegion internals.

## Persistence

Stage 1 Device state is intentionally in-memory only. Existing .qs files and
Project serialization are unchanged. A future backwards-compatible persistence
migration must serialize regions, source structures, transforms, roles, device
cell/PBC, transport direction, and membership-related metadata.

## Deferred Stage 2 work

No automatic placement, interface matching, region supercells, collision
detection, templates, device undo/redo, transport workflows, electrodes,
principal layers, gates, NEGF, or Device persistence is implemented here.
