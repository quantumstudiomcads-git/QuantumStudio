"""Widget-free DeviceRegion placement and device-cell geometry helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


_EPSILON = 1.0e-10
MAX_REPEAT_COUNT = 10


@dataclass(frozen=True)
class RegionBounds:
    """Cartesian bounds for a region's current transformed geometry."""

    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    @property
    def center(self) -> tuple[float, float, float]:
        return tuple((low + high) / 2.0 for low, high in zip(self.minimum, self.maximum))


def _finite_vector(values: Iterable[float], label: str, *, nonnegative: bool = False) -> np.ndarray:
    vector = np.asarray(tuple(values), dtype=float)
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{label} must contain three finite values.")
    if nonnegative and np.any(vector < 0.0):
        raise ValueError(f"{label} values must be non-negative.")
    return vector


def transformed_region_bounds(region) -> RegionBounds:
    """Return bounds of ``region`` after its non-destructive transform."""
    transformed = region.transformed_structure()
    if not transformed.atoms:
        raise ValueError(f"Region {region.id} has no atoms to place.")
    positions = np.asarray([(atom.x, atom.y, atom.z) for atom in transformed.atoms], dtype=float)
    if not np.all(np.isfinite(positions)):
        raise ValueError(f"Region {region.id} has non-finite transformed coordinates.")
    return RegionBounds(
        minimum=tuple(float(value) for value in positions.min(axis=0)),
        maximum=tuple(float(value) for value in positions.max(axis=0)),
    )


def visible_device_bounds(device) -> RegionBounds:
    """Return current visible-device bounds in assembled Cartesian coordinates."""
    bounds = [transformed_region_bounds(region) for region in device.regions if region.visible]
    if not bounds:
        raise ValueError("Device has no visible atoms to fit.")
    origin_offset = _finite_vector(getattr(device, "origin_offset", (0.0, 0.0, 0.0)), "Device origin offset")
    minimum = np.min(np.asarray([bound.minimum for bound in bounds], dtype=float), axis=0) + origin_offset
    maximum = np.max(np.asarray([bound.maximum for bound in bounds], dtype=float), axis=0) + origin_offset
    return RegionBounds(tuple(float(value) for value in minimum), tuple(float(value) for value in maximum))


def translate_region(region, correction: Iterable[float]) -> tuple[float, float, float]:
    """Apply a device-level translation correction without touching the source Structure."""
    correction = _finite_vector(correction, "Translation correction")
    current = _finite_vector(region.translation, "Region translation")
    region.translation = tuple(float(value) for value in current + correction)
    return tuple(float(value) for value in correction)


def _placement_axis(direction: str) -> tuple[int, int]:
    direction = str(direction).strip().lower()
    mapping = {
        "above": (2, +1), "below": (2, -1),
        "right": (0, +1), "left": (0, -1),
    }
    if direction not in mapping:
        raise ValueError("Placement direction must be Above, Below, Left, or Right.")
    return mapping[direction]


def place_region(moving_region, reference_region, direction: str, gap: float = 3.0) -> tuple[float, float, float]:
    """Place a moving region beside a reference region using outermost atom bounds."""
    if moving_region.id == reference_region.id:
        raise ValueError("The moving and reference regions must be different.")
    gap = float(gap)
    if not np.isfinite(gap) or gap < 0.0:
        raise ValueError("Placement gap must be a finite non-negative value in Å.")
    axis, side = _placement_axis(direction)
    moving = transformed_region_bounds(moving_region)
    reference = transformed_region_bounds(reference_region)
    if side > 0:
        correction = reference.maximum[axis] + gap - moving.minimum[axis]
    else:
        correction = reference.minimum[axis] - gap - moving.maximum[axis]
    delta = np.zeros(3, dtype=float)
    delta[axis] = correction
    return translate_region(moving_region, delta)


def align_region_centers(moving_region, reference_region, axes: str = "XYZ") -> tuple[float, float, float]:
    """Align requested bounding-box center axes of a moving region to a reference."""
    if moving_region.id == reference_region.id:
        raise ValueError("The moving and reference regions must be different.")
    requested = str(axes).upper()
    if requested not in {"X", "Y", "Z", "XY", "XZ", "YZ", "XYZ"}:
        raise ValueError("Center alignment axes must be X, Y, Z, XY, XZ, YZ, or XYZ.")
    moving = np.asarray(transformed_region_bounds(moving_region).center, dtype=float)
    reference = np.asarray(transformed_region_bounds(reference_region).center, dtype=float)
    delta = np.zeros(3, dtype=float)
    for axis, letter in enumerate("XYZ"):
        if letter in requested:
            delta[axis] = reference[axis] - moving[axis]
    return translate_region(moving_region, delta)


def align_region_surface(moving_region, reference_region, surface: str) -> tuple[float, float, float]:
    """Align equal named axis-aligned bounding planes of two regions."""
    if moving_region.id == reference_region.id:
        raise ValueError("The moving and reference regions must be different.")
    surface = str(surface).strip().lower()
    mapping = {
        "top": (2, "maximum"), "bottom": (2, "minimum"),
        "left": (0, "minimum"), "right": (0, "maximum"),
    }
    if surface not in mapping:
        raise ValueError("Surface must be Top, Bottom, Left, or Right.")
    axis, attribute = mapping[surface]
    moving = transformed_region_bounds(moving_region)
    reference = transformed_region_bounds(reference_region)
    delta = np.zeros(3, dtype=float)
    delta[axis] = getattr(reference, attribute)[axis] - getattr(moving, attribute)[axis]
    return translate_region(moving_region, delta)


def validate_repeat_counts(counts: Iterable[int]) -> tuple[int, int, int]:
    values = tuple(int(value) for value in counts)
    if len(values) != 3 or any(value < 1 or value > MAX_REPEAT_COUNT for value in values):
        raise ValueError(f"Repeat counts must be integers between 1 and {MAX_REPEAT_COUNT}.")
    return values


def repeat_region(device, region_id: str, nx: int = 1, ny: int = 1, nz: int = 1):
    """Create independent region copies over the selected region's oriented source cell."""
    region = device.get_region(region_id)
    if region is None:
        raise KeyError(f"Unknown region id: {region_id}")
    counts = validate_repeat_counts((nx, ny, nz))
    cell = np.asarray(region.transformed_structure().cell, dtype=float)
    if cell.shape != (3, 3) or not np.all(np.isfinite(cell)) or abs(float(np.linalg.det(cell))) <= _EPSILON:
        raise ValueError("Region repetition requires a finite nonsingular source cell.")
    base_translation = _finite_vector(region.translation, "Region translation")
    duplicates = []
    for i in range(counts[0]):
        for j in range(counts[1]):
            for k in range(counts[2]):
                if (i, j, k) == (0, 0, 0):
                    continue
                duplicate = region.duplicate(name=f"{region.name} ({i + 1},{j + 1},{k + 1})")
                displacement = i * cell[0] + j * cell[1] + k * cell[2]
                duplicate.translation = tuple(float(value) for value in base_translation + displacement)
                device.add_region(duplicate)
                duplicates.append(duplicate)
    return tuple(duplicates)


def set_device_padding(device, padding: Iterable[float]) -> tuple[float, float, float]:
    """Set Device-level padding without deriving or changing a Device cell."""
    values = _finite_vector(padding, "Device padding", nonnegative=True)
    device.padding = tuple(float(value) for value in values)
    return device.padding


def fit_device_cell(device, padding: Iterable[float] = (5.0, 5.0, 5.0)) -> RegionBounds:
    """Fit an axis-aligned Device cell without changing relative region transforms."""
    padding = _finite_vector(padding, "Device padding", nonnegative=True)
    bounds = visible_device_bounds(device)
    minimum = np.asarray(bounds.minimum, dtype=float)
    maximum = np.asarray(bounds.maximum, dtype=float)
    lengths = maximum - minimum + 2.0 * padding
    if not np.all(np.isfinite(lengths)) or np.any(lengths <= _EPSILON):
        raise ValueError("Unable to derive a valid Device cell from current geometry.")
    current_origin = _finite_vector(getattr(device, "origin_offset", (0.0, 0.0, 0.0)), "Device origin offset")
    device.origin_offset = tuple(float(value) for value in current_origin + padding - minimum)
    set_device_padding(device, padding)
    device.cell = np.diag(lengths).tolist()
    return RegionBounds(tuple(float(value) for value in padding), tuple(float(value) for value in padding + maximum - minimum))
