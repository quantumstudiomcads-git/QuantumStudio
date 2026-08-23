from dataclasses import dataclass, field
import numpy as np
from frontend.core.structure import Structure
from frontend.device_builder.model.device import VALID_TRANSPORT_DIRECTIONS

@dataclass
class DeviceValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self):
        return not self.errors

    def require_valid(self):
        if self.errors:
            raise ValueError("; ".join(self.errors))

def validate_device(device, assembled_structure=None):
    result = DeviceValidationResult()
    if not isinstance(getattr(device, "id", None), str) or not device.id.strip():
        result.errors.append("Device requires a non-empty id.")
    if not isinstance(getattr(device, "name", None), str) or not device.name.strip():
        result.errors.append("Device requires a non-empty name.")
    region_ids = [region.id for region in getattr(device, "regions", ())]
    if len(region_ids) != len(set(region_ids)):
        result.errors.append("Device region ids must be unique.")
    for region in getattr(device, "regions", ()):
        if not isinstance(region.source_structure, Structure):
            result.errors.append(f"Region {region.id} has no valid source Structure.")
        for label, values in (("translation", region.translation), ("rotation", region.rotation)):
            array = np.asarray(values, dtype=float)
            if array.shape != (3,) or not np.all(np.isfinite(array)):
                result.errors.append(f"Region {region.id} has invalid {label}.")
    periodic = getattr(device, "periodic", None)
    if not isinstance(periodic, (list, tuple)) or len(periodic) != 3 or not all(isinstance(value, (bool, np.bool_)) for value in periodic):
        result.errors.append("Device PBC must contain three Boolean values.")
    if getattr(device, "transport_direction", None) not in VALID_TRANSPORT_DIRECTIONS:
        result.errors.append("Device transport direction must be X, Y, or Z.")
    if getattr(device, "cell", None) is not None:
        cell = np.asarray(device.cell, dtype=float)
        if cell.shape != (3, 3) or not np.all(np.isfinite(cell)):
            result.errors.append("Device cell must be a finite 3x3 matrix.")
        elif abs(float(np.linalg.det(cell))) <= 1e-10:
            result.errors.append("Device cell must be nonsingular.")
    if assembled_structure is not None:
        positions = np.asarray([(atom.x, atom.y, atom.z) for atom in assembled_structure.atoms], dtype=float)
        if positions.size and not np.all(np.isfinite(positions)):
            result.errors.append("Assembled coordinates must be finite.")
    return result
