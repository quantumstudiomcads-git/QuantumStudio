"""Deterministic full Brillouin-zone grids for optical NSCF calculations."""
from __future__ import annotations

from dataclasses import dataclass
from math import isclose


class OpticalGridError(ValueError):
    pass


def full_bz_grid(mesh):
    mesh = tuple(mesh)
    if len(mesh) != 3 or any(isinstance(n, bool) or int(n) != n or int(n) < 1 for n in mesh):
        raise OpticalGridError("A full optical grid requires three positive integer dimensions.")
    nx, ny, nz = (int(n) for n in mesh)
    return tuple((i / nx, j / ny, k / nz) for k in range(nz) for j in range(ny) for i in range(nx))


def _canonical(point):
    return tuple(round(float(value) % 1.0, 12) for value in point)


@dataclass(frozen=True)
class OpticalGridValidation:
    expected_count: int
    point_count: int
    unique_count: int
    weight_min: float
    weight_max: float
    weight_sum: float
    weight_residual: float

    @property
    def valid(self):
        return (self.point_count == self.expected_count and self.unique_count == self.expected_count
                and self.weight_residual <= 1e-10 and self.weight_max - self.weight_min <= 1e-12)


def validate_full_bz_grid(mesh, points, weights=None, *, tolerance=1e-10):
    expected = len(full_bz_grid(mesh))
    points = tuple(tuple(float(x) for x in point) for point in points)
    if any(len(point) != 3 for point in points):
        raise OpticalGridError("Optical reciprocal coordinates must have three components.")
    unique = {_canonical(point) for point in points}
    if weights is None:
        weights = (1.0 / expected,) * len(points)
    weights = tuple(float(w) for w in weights)
    if len(weights) != len(points) or any(w <= 0 for w in weights):
        raise OpticalGridError("Optical full-grid weights must be positive and match the point count.")
    expected_weight = 1.0 / expected
    result = OpticalGridValidation(expected, len(points), len(unique), min(weights, default=0.0), max(weights, default=0.0), sum(weights), abs(sum(weights) - 1.0))
    if result.point_count != expected or result.unique_count != expected:
        raise OpticalGridError(f"Optical grid requires {expected} unique points; received {result.point_count} ({result.unique_count} unique).")
    if result.weight_residual > tolerance or any(abs(w - expected_weight) > tolerance for w in weights):
        raise OpticalGridError("Optical full-BZ weights must be equal and sum to one.")
    return result
