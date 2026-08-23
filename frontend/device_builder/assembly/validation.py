from dataclasses import dataclass, field
import numpy as np
from frontend.core.structure import Structure
from frontend.device_builder.model.device import VALID_TRANSPORT_DIRECTIONS
from frontend.device_builder.model.interface import DeviceInterface, InterfaceMode, VALID_INTERFACE_STRAIN_MODES


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


def validate_device(device, assembled_structure=None, *, allow_empty=False, check_collisions=False, collision_scale=None):
    result = DeviceValidationResult()
    if not isinstance(getattr(device, "id", None), str) or not device.id.strip():
        result.errors.append("Device requires a non-empty id.")
    if not isinstance(getattr(device, "name", None), str) or not device.name.strip():
        result.errors.append("Device requires a non-empty name.")
    region_ids = [region.id for region in getattr(device, "regions", ())]
    if not region_ids and not allow_empty:
        result.errors.append("Device must contain at least one region.")
    if len(region_ids) != len(set(region_ids)):
        result.errors.append("Device region ids must be unique.")
    interface_ids = [interface.id for interface in getattr(device, "interfaces", ())]
    if len(interface_ids) != len(set(interface_ids)):
        result.errors.append("Device interface ids must be unique.")
    for region in getattr(device, "regions", ()):
        if not isinstance(region.source_structure, Structure):
            result.errors.append(f"Region {region.id} has no valid source Structure.")
        for label, values in (("translation", region.translation), ("rotation", region.rotation)):
            array = np.asarray(values, dtype=float)
            if array.shape != (3,) or not np.all(np.isfinite(array)):
                result.errors.append(f"Region {region.id} has invalid {label}.")
    known_region_ids = set(region_ids)
    for interface in getattr(device, "interfaces", ()):
        if not isinstance(interface, DeviceInterface):
            result.errors.append("Device interfaces must be DeviceInterface instances.")
            continue
        if interface.region_a_id not in known_region_ids or interface.region_b_id not in known_region_ids:
            result.errors.append(f"Interface {interface.id} references an unknown region.")
        if interface.region_a_id == interface.region_b_id:
            result.errors.append(f"Interface {interface.id} must reference two different regions.")
        if interface.mode not in (InterfaceMode.ALIGNED, InterfaceMode.TWISTED):
            result.errors.append(f"Interface {interface.id} has an invalid mode.")
        if not np.isfinite(interface.requested_twist_deg):
            result.errors.append(f"Interface {interface.id} has invalid requested twist.")
        if not np.isfinite(interface.max_strain) or interface.max_strain < 0.0:
            result.errors.append(f"Interface {interface.id} has invalid max strain.")
        if interface.strain_mode not in VALID_INTERFACE_STRAIN_MODES:
            result.errors.append(f"Interface {interface.id} has invalid strain mode.")
        if not np.isfinite(interface.gap) or interface.gap < 0.0:
            result.errors.append(f"Interface {interface.id} has invalid gap.")
        if int(interface.max_index) < 1:
            result.errors.append(f"Interface {interface.id} has invalid max_index.")
        if not isinstance(interface.diagnostics, dict) or not isinstance(interface.metadata, dict):
            result.errors.append(f"Interface {interface.id} has invalid metadata.")
    periodic = getattr(device, "periodic", None)
    if not isinstance(periodic, (list, tuple)) or len(periodic) != 3 or not all(isinstance(value, (bool, np.bool_)) for value in periodic):
        result.errors.append("Device PBC must contain three Boolean values.")
    if getattr(device, "transport_direction", None) not in VALID_TRANSPORT_DIRECTIONS:
        result.errors.append("Device transport direction must be X, Y, or Z.")
    for label, values, nonnegative in (
        ("Device padding", getattr(device, "padding", (5.0, 5.0, 5.0)), True),
        ("Device origin offset", getattr(device, "origin_offset", (0.0, 0.0, 0.0)), False),
    ):
        array = np.asarray(values, dtype=float)
        if array.shape != (3,) or not np.all(np.isfinite(array)) or (nonnegative and np.any(array < 0.0)):
            qualifier = "non-negative " if nonnegative else ""
            result.errors.append(f"{label} must contain three finite {qualifier}values.")
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
        if positions.size and getattr(device, "cell", None) is not None and not result.errors:
            cell = np.asarray(device.cell, dtype=float)
            fractional = positions @ np.linalg.inv(cell)
            tolerance = 1.0e-8
            if np.any(fractional < -tolerance) or np.any(fractional > 1.0 + tolerance):
                result.warnings.append("Assembled geometry extends outside the explicit Device cell.")
    if check_collisions and not result.errors:
        from .collisions import DEFAULT_COLLISION_SCALE, detect_inter_region_collisions
        collisions = detect_inter_region_collisions(device, DEFAULT_COLLISION_SCALE if collision_scale is None else collision_scale)
        if collisions:
            result.warnings.append(f"{len(collisions)} possible inter-region atomic overlap(s) detected.")
    return result
