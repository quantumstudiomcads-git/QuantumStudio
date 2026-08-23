import math
import numpy as np
from frontend.core.structure import Structure

def rotation_matrix_xyz(rotation_deg):
    """Return R = Rz @ Ry @ Rx for global X, Y, Z rotations in degrees."""
    values = np.asarray(rotation_deg, dtype=float)
    if values.shape != (3,) or not np.all(np.isfinite(values)):
        raise ValueError("Rotation must be three finite degree values.")
    rx, ry, rz = np.radians(values)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    rotation_x = np.array(((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx)))
    rotation_y = np.array(((cy, 0.0, sy), (0.0, 1.0, 0.0), (-sy, 0.0, cy)))
    rotation_z = np.array(((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0)))
    return rotation_z @ rotation_y @ rotation_x

def transform_structure(structure, translation, rotation_deg, reference_point=(0.0, 0.0, 0.0)):
    """Return a transformed copy. Source Structure is never mutated."""
    if not isinstance(structure, Structure):
        raise TypeError("Device region source must be a Quantum Studio Structure.")
    translation = np.asarray(translation, dtype=float)
    reference_point = np.asarray(reference_point, dtype=float)
    if translation.shape != (3,) or reference_point.shape != (3,):
        raise ValueError("Translation and reference point must be 3-vectors.")
    if not np.all(np.isfinite(translation)) or not np.all(np.isfinite(reference_point)):
        raise ValueError("Translation and reference point must be finite.")
    rotation = rotation_matrix_xyz(rotation_deg)
    transformed = structure.copy()
    for atom in transformed.atoms:
        position = np.array((atom.x, atom.y, atom.z), dtype=float)
        position = (position - reference_point) @ rotation.T + reference_point + translation
        atom.x, atom.y, atom.z = (float(value) for value in position)
    cell = np.asarray(transformed.cell, dtype=float)
    if cell.shape == (3, 3) and np.all(np.isfinite(cell)):
        transformed.cell = (cell @ rotation.T).tolist()
    return transformed
