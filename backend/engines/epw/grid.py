"""EPW 6.1 full coarse-electronic-grid contract."""
from __future__ import annotations
from dataclasses import dataclass
from math import isclose
from typing import Iterable

class EPWGridError(ValueError):
    pass

def require_finer_mesh(coarse, fine):
    """Require a genuinely finer, component-wise commensurate EPW mesh."""
    coarse = tuple(int(x) for x in coarse)
    fine = tuple(int(x) for x in fine)
    if len(coarse) != 3 or len(fine) != 3 or any(x < 1 for x in (*coarse, *fine)):
        raise EPWGridError("EPW meshes must contain three positive dimensions.")
    if not all(f > c for f, c in zip(fine, coarse)):
        raise EPWGridError("Fine EPW mesh must be finer than the coarse mesh in every direction.")
    if any(f % c for f, c in zip(fine, coarse)):
        raise EPWGridError("Fine EPW mesh must be commensurate with the coarse mesh.")
    return fine

@dataclass(frozen=True)
class EPWGridValidation:
    expected_count: int
    loaded_count: int
    unique_count: int
    weight_sum: float
    max_coordinate_difference: float
    ordering_matches: bool

def epw_full_grid(mesh: tuple[int, int, int] | list[int]) -> tuple[tuple[float, float, float], ...]:
    if len(mesh) != 3 or any(int(n) != n or int(n) < 1 for n in mesh):
        raise EPWGridError("EPW coarse grid dimensions must be three positive integers.")
    n1, n2, n3 = (int(n) for n in mesh)
    # EPW's kgen.f90 order is k outer, i middle, j inner, with [0,1) points.
    return tuple((j / n1, i / n2, k / n3) for k in range(n3) for i in range(n2) for j in range(n1))

def _canonical(point):
    return tuple(round(float(x) % 1.0, 12) for x in point)

def validate_epw_grid(mesh, loaded_points: Iterable[Iterable[float]], weights=None, *, tolerance=1e-10) -> EPWGridValidation:
    expected = epw_full_grid(tuple(mesh))
    loaded = tuple(tuple(float(x) for x in point) for point in loaded_points)
    if any(len(point) != 3 for point in loaded):
        raise EPWGridError("EPW coarse electronic coordinates must have three components.")
    unique = {_canonical(point) for point in loaded}
    if len(unique) != len(loaded):
        raise EPWGridError("EPW coarse electronic grid contains duplicate points.")
    if len(loaded) != len(expected):
        raise EPWGridError(f"EPW requires a complete {mesh[0]}x{mesh[1]}x{mesh[2]} coarse electronic grid ({len(expected)} k points), but the selected QE artifact contains {len(loaded)} points.")
    diffs = [max(abs(a-b) for a,b in zip(exp, got)) for exp,got in zip(expected, loaded)]
    maximum = max(diffs, default=0.0)
    ordering = maximum <= tolerance
    if not ordering:
        raise EPWGridError(f"EPW coarse electronic grid coordinates/order differ from the frozen convention (maximum difference {maximum:g}).")
    if weights is None:
        total = 1.0
    else:
        values = tuple(float(w) for w in weights)
        if len(values) != len(loaded):
            raise EPWGridError("EPW coarse electronic weights do not match the k-point count.")
        if any(w <= 0 for w in values) or not isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=tolerance):
            raise EPWGridError("EPW coarse electronic weights must be positive and sum to one.")
        total = sum(values)
    return EPWGridValidation(len(expected), len(loaded), len(unique), total, maximum, ordering)

def qe_full_grid_card(mesh):
    points = epw_full_grid(tuple(mesh))
    weight = 1.0 / len(points)
    rows = ["K_POINTS crystal", str(len(points))]
    rows.extend(f"{x:.12f} {y:.12f} {z:.12f} {weight:.12f}" for x,y,z in points)
    return "\n".join(rows)
