from dataclasses import dataclass
import numpy as np
from frontend.core.structure import Atom, Structure
from .validation import validate_device

@dataclass(frozen=True)
class DeviceAssembly:
    structure: Structure
    atom_region_ids: tuple[str, ...]

def _derived_preview_cell(atoms):
    if not atoms:
        return [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 10.0]]
    positions = np.asarray([(atom.x, atom.y, atom.z) for atom in atoms], dtype=float)
    lengths = np.maximum(positions.max(axis=0) - positions.min(axis=0), 1.0) + 10.0
    return np.diag(lengths).tolist()

def assemble_device(device):
    validate_device(device).require_valid()
    atoms, membership = [], []
    for region in device.regions:
        if not region.visible:
            continue
        transformed = region.transformed_structure()
        for atom in transformed.atoms:
            atoms.append(Atom(atom.element, atom.x, atom.y, atom.z))
            membership.append(region.id)
    cell = device.cell if device.cell is not None else _derived_preview_cell(atoms)
    periodic = list(device.periodic) if device.cell is not None else [False, False, False]
    structure = Structure(atoms=atoms, cell=[[float(value) for value in vector] for vector in cell], name=device.name)
    structure.periodic = periodic
    validate_device(device, assembled_structure=structure).require_valid()
    return DeviceAssembly(structure=structure, atom_region_ids=tuple(membership))
