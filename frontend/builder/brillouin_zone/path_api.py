"""Qt-free recommended high-symmetry paths for a request structure snapshot.

This deliberately lives with the Brillouin-zone subsystem.  Calculate consumes its
small public value objects and never owns a second crystallographic path database.
The initial classifier is conservative: it advertises a recommendation only for the
well-defined cubic and hexagonal metric cases and otherwise asks for an explicit path.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, sqrt
from typing import Mapping


@dataclass(frozen=True)
class HighSymmetryPoint:
    label: str
    coordinates: tuple[float, float, float]


@dataclass(frozen=True)
class RecommendedSegment:
    start: HighSymmetryPoint
    end: HighSymmetryPoint

    @property
    def label(self) -> str:
        return f"{self.start.label} → {self.end.label}"


@dataclass(frozen=True)
class BandPathRecommendation:
    bravais_label: str
    segments: tuple[RecommendedSegment, ...]
    message: str = ""


def normalize_band_path(path: object) -> list[dict[str, object]]:
    """Return the single serializable BandPath representation used by Calculate."""
    if not isinstance(path, (list, tuple)):
        return []
    normalized = []
    for point in path:
        if not isinstance(point, Mapping):
            raise ValueError("Band path points must be mappings.")
        coordinates = point.get("coordinates")
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 3:
            raise ValueError("Band path points require three fractional coordinates.")
        count = int(point.get("points", 40))
        if count < 1:
            raise ValueError("Band path interpolation counts must be positive.")
        normalized.append({"label": str(point.get("label", "")).strip(), "coordinates": [float(value) for value in coordinates], "points": count})
    if normalized and len(normalized) < 2:
        raise ValueError("Band path requires at least two points.")
    return normalized

def band_path_summary(path: object) -> str:
    points = normalize_band_path(path)
    return " — ".join(str(point["label"]) for point in points) if points else "Not selected"


def _length(vector: object) -> float:
    return sqrt(sum(float(value) ** 2 for value in vector))


def _angle(left: object, right: object) -> float:
    denominator = _length(left) * _length(right)
    if denominator <= 0:
        return 0.0
    cosine = max(-1.0, min(1.0, sum(float(a) * float(b) for a, b in zip(left, right)) / denominator))
    return degrees(acos(cosine))


def _close(left: float, right: float, tolerance: float = 1e-4) -> bool:
    return abs(left - right) <= tolerance * max(1.0, abs(left), abs(right))


def recommended_band_path(structure: Mapping[str, object]) -> BandPathRecommendation:
    """Return ordered, snapshot-derived path segments for supported cell metrics.

    Coordinates are QE-compatible fractional reciprocal coordinates.  The result is
    intentionally a recommendation, not a symmetry-analysis claim for arbitrary cells.
    """
    cell = structure.get("cell") if isinstance(structure, Mapping) else None
    periodic = structure.get("periodic", (True, True, True)) if isinstance(structure, Mapping) else ()
    if not isinstance(cell, (list, tuple)) or len(cell) != 3 or not all(isinstance(row, (list, tuple)) and len(row) == 3 for row in cell):
        return BandPathRecommendation("Unknown", (), "A valid request cell is required for a recommended band path.")
    if not isinstance(periodic, (list, tuple)) or len(periodic) != 3 or not any(bool(value) for value in periodic):
        return BandPathRecommendation("Non-periodic", (), "A periodic structure is required for a reciprocal-space path.")
    a, b, c = (_length(vector) for vector in cell)
    alpha, beta, gamma = _angle(cell[1], cell[2]), _angle(cell[0], cell[2]), _angle(cell[0], cell[1])
    gamma_point = HighSymmetryPoint("Γ", (0.0, 0.0, 0.0))
    if _close(a, b) and _close(gamma, 120.0) and _close(alpha, 90.0) and _close(beta, 90.0):
        m = HighSymmetryPoint("M", (0.5, 0.0, 0.0))
        k = HighSymmetryPoint("K", (1.0 / 3.0, 1.0 / 3.0, 0.0))
        return BandPathRecommendation("Hexagonal", (RecommendedSegment(gamma_point, m), RecommendedSegment(m, k), RecommendedSegment(k, gamma_point)))
    if _close(a, b) and _close(b, c) and all(_close(value, 90.0) for value in (alpha, beta, gamma)):
        x = HighSymmetryPoint("X", (0.0, 0.5, 0.0))
        w = HighSymmetryPoint("W", (0.25, 0.5, 0.0))
        k = HighSymmetryPoint("K", (0.375, 0.375, 0.0))
        l = HighSymmetryPoint("L", (0.5, 0.5, 0.5))
        return BandPathRecommendation("Cubic", (RecommendedSegment(gamma_point, x), RecommendedSegment(x, w), RecommendedSegment(w, k), RecommendedSegment(k, gamma_point), RecommendedSegment(gamma_point, l)))
    return BandPathRecommendation("Unclassified", (), "No conservative recommended path is available for this cell; use Custom Path.")


def materialize_path(segments: tuple[RecommendedSegment, ...], enabled: tuple[bool, ...], points_per_segment: int) -> list[dict[str, object]]:
    """Build an ordered typed BandPath without silently bridging disconnected choices."""
    selected = [segment for segment, checked in zip(segments, enabled) if checked]
    if not selected:
        return []
    points: list[HighSymmetryPoint] = [selected[0].start]
    for segment in selected:
        if points[-1] != segment.start:
            raise ValueError("Selected high-symmetry segments are disconnected.")
        points.append(segment.end)
    return [{"label": point.label, "coordinates": list(point.coordinates), "points": int(points_per_segment)} for point in points]
