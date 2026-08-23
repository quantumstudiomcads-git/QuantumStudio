"""Pure crystallographic/viewer mathematics for the Builder workspace."""

from __future__ import annotations

import math
import numpy as np


def _validated_cell(cell):
    value = np.asarray(cell, dtype=float)
    if value.shape != (3, 3) or not np.all(np.isfinite(value)):
        raise ValueError("Cell must be a finite (3, 3) matrix.")
    volume = float(np.linalg.det(value))
    if abs(volume) <= 1e-12:
        raise ValueError("Cell is singular; crystallographic directions are unavailable.")
    return value, volume


def reciprocal_lattice(cell):
    """Return reciprocal row vectors including the conventional 2π factor."""
    value, volume = _validated_cell(cell)
    a, b, c = value
    return 2.0 * math.pi * np.array([
        np.cross(b, c) / volume,
        np.cross(c, a) / volume,
        np.cross(a, b) / volume,
    ])


def miller_normal(cell, h, k, l):
    indices = np.asarray([int(h), int(k), int(l)], dtype=int)
    if not np.any(indices):
        raise ValueError("Miller indices (0, 0, 0) do not define a plane.")
    return indices @ reciprocal_lattice(cell)


def fractional_coordinates(cartesian, cell):
    value, _ = _validated_cell(cell)
    point = np.asarray(cartesian, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError("Cartesian coordinate must be a finite length-3 vector.")
    return point @ np.linalg.inv(value)


def cartesian_coordinates(fractional, cell):
    value, _ = _validated_cell(cell)
    point = np.asarray(fractional, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError("Fractional coordinate must be a finite length-3 vector.")
    return point @ value


def minimum_image_displacement(displacement, cell, pbc=(True, True, True)):
    value, _ = _validated_cell(cell)
    delta = np.asarray(displacement, dtype=float)
    if delta.shape != (3,) or not np.all(np.isfinite(delta)):
        raise ValueError("Displacement must be a finite length-3 vector.")
    fractional = delta @ np.linalg.inv(value)
    periodic = np.asarray(pbc, dtype=bool)
    if periodic.shape != (3,):
        raise ValueError("PBC must contain three boolean values.")
    fractional[periodic] -= np.round(fractional[periodic])
    return fractional @ value


def minimum_image_distance(position_a, position_b, cell, pbc=(True, True, True)):
    return float(np.linalg.norm(minimum_image_displacement(
        np.asarray(position_b, dtype=float) - np.asarray(position_a, dtype=float),
        cell, pbc,
    )))
