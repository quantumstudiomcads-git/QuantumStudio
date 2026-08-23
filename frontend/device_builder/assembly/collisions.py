"""Inter-region overlap diagnostics for Device Builder geometry."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from ase.data import atomic_numbers, covalent_radii


DEFAULT_COLLISION_SCALE = 0.75


@dataclass(frozen=True)
class DeviceCollision:
    region_a_id: str
    region_b_id: str
    atom_a_index: int
    atom_b_index: int
    distance: float
    threshold: float


def covalent_radius(element: str) -> float:
    """Return the ASE covalent radius for a valid element symbol."""
    try:
        number = atomic_numbers[str(element)]
        radius = float(covalent_radii[number])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"No covalent radius is available for element {element!r}.") from error
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError(f"No positive covalent radius is available for element {element!r}.")
    return radius


def detect_inter_region_collisions(device, scale: float = DEFAULT_COLLISION_SCALE) -> tuple[DeviceCollision, ...]:
    """Report direct-Cartesian close contacts between distinct visible regions only."""
    scale = float(scale)
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("Collision scale must be a positive finite value.")
    regions = [(region, region.transformed_structure()) for region in device.regions if region.visible]
    collisions = []
    for left_index, (left_region, left_structure) in enumerate(regions):
        for right_region, right_structure in regions[left_index + 1:]:
            for atom_a_index, atom_a in enumerate(left_structure.atoms):
                position_a = np.asarray((atom_a.x, atom_a.y, atom_a.z), dtype=float)
                radius_a = covalent_radius(atom_a.element)
                for atom_b_index, atom_b in enumerate(right_structure.atoms):
                    position_b = np.asarray((atom_b.x, atom_b.y, atom_b.z), dtype=float)
                    radius_b = covalent_radius(atom_b.element)
                    distance = float(np.linalg.norm(position_b - position_a))
                    threshold = scale * (radius_a + radius_b)
                    if distance < threshold:
                        collisions.append(DeviceCollision(
                            region_a_id=left_region.id,
                            region_b_id=right_region.id,
                            atom_a_index=atom_a_index,
                            atom_b_index=atom_b_index,
                            distance=distance,
                            threshold=float(threshold),
                        ))
    return tuple(collisions)
