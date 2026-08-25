"""Conservative, Qt-free derived electronic analysis over structured band results."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

# Shared scientific policy.  This deliberately governs degeneracy, physical-k
# equivalence and the zero-gap boundary in one place rather than scattered UI epsilons.
TOLERANCE = 1e-6


@dataclass(frozen=True)
class BandEdge:
    energy: float
    band_index: int
    path_sample_index: int
    path_coordinate: float | None = None
    kpoint: tuple[float, ...] | None = None
    spin: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class BandGapAnalysis:
    status: str
    gap_scope: str = "sampled_path"
    gap: float | None = None
    classification: str = "UNRESOLVED"
    vbm: BandEdge | None = None
    cbm: BandEdge | None = None
    degenerate_vbm: tuple[BandEdge, ...] = ()
    degenerate_cbm: tuple[BandEdge, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class FitDirection:
    """One continuously sampled physical path direction from an edge."""
    label: str
    sample_indices: tuple[int, ...]
    one_sided: bool = True


@dataclass(frozen=True)
class EffectiveMassFit:
    status: str
    edge: str
    mass_me: float | None = None
    curvature: float | None = None
    coefficients: tuple[float, ...] = ()
    r_squared: float | None = None
    sample_count: int = 0
    k_range: tuple[float, float] | None = None
    direction: str = ""
    warnings: tuple[str, ...] = ()
    sample_distances: tuple[float, ...] = ()
    sample_energies: tuple[float, ...] = ()
    fitted_energies: tuple[float, ...] = ()
    one_sided: bool = False


@dataclass(frozen=True)
class ElectronicAnalysisResult:
    gap: BandGapAnalysis
    fits: tuple[EffectiveMassFit, ...] = ()
    result_id: str = ""


def _bands(result):
    values = result.arrays.get("energies", result.arrays.get("energy"))
    if values is None:
        return None
    values = np.asarray(values, dtype=float)
    return values[:, None] if values.ndim == 1 else values


def _kpoints(result, count):
    values = result.arrays.get("kpoints", result.metadata.get("kpoints"))
    if values is None:
        return [None] * count
    values = np.asarray(values, dtype=float)
    return [tuple(row.tolist()) for row in values[:count]]


def _occupied_mask(result, shape, tolerance):
    occupations = result.metadata.get("occupations", result.arrays.get("occupations"))
    if occupations is not None:
        occupations = np.asarray(occupations, dtype=float)
        # Fractional occupation is the available structured evidence for a crossing.
        if np.any((occupations > tolerance) & (occupations < 1.0 - tolerance)):
            return None, "METALLIC"
        return occupations > 0.5, None
    count = result.metadata.get("occupied_band_count", result.metadata.get("n_occupied"))
    if count is not None:
        mask = np.zeros(shape, dtype=bool)
        mask[:, : min(int(count), shape[1])] = True
        return mask, None
    if result.metadata.get("metallic") is True:
        return None, "METALLIC"
    return None, "UNRESOLVED_OCCUPANCY"


def _edge_label(result, sample):
    labels = result.metadata.get("path_labels", {})
    if isinstance(labels, dict):
        return labels.get(str(sample), labels.get(sample))
    if isinstance(labels, (list, tuple)) and sample < len(labels):
        return labels[sample]
    return None


def analyze_band_edges(result, *, tolerance=TOLERANCE):
    """Identify defensible sampled-path edges without changing the source Result."""
    bands = _bands(result)
    if bands is None:
        return BandGapAnalysis("UNRESOLVED_OCCUPANCY", warnings=("Band energies are unavailable.",))
    mask, reason = _occupied_mask(result, bands.shape, tolerance)
    if reason:
        warning = "Occupied and unoccupied bands cannot be identified from stored metadata."
        if reason == "METALLIC":
            warning = "Structured occupations indicate a partially occupied band."
        return BandGapAnalysis(reason, warnings=(warning,))
    if not np.any(mask) or not np.any(~mask):
        return BandGapAnalysis("UNRESOLVED_OCCUPANCY", warnings=("Both occupied and unoccupied states are required.",))
    occupied = np.where(mask, bands, np.nan)
    unoccupied = np.where(~mask, bands, np.nan)
    vmax, cmin = float(np.nanmax(occupied)), float(np.nanmin(unoccupied))
    kpoints = _kpoints(result, bands.shape[0])
    path = np.asarray(result.arrays.get("path_coordinate", np.arange(bands.shape[0])), dtype=float)

    def edge(value, band_index, sample):
        coordinate = float(path[sample]) if sample < len(path) else None
        return BandEdge(value, band_index, sample, coordinate, kpoints[sample], None, _edge_label(result, sample))

    vi = np.argwhere(np.isclose(occupied, vmax, atol=tolerance))
    ci = np.argwhere(np.isclose(unoccupied, cmin, atol=tolerance))
    vbm_candidates = tuple(edge(float(bands[i, j]), int(j), int(i)) for i, j in vi)
    cbm_candidates = tuple(edge(float(bands[i, j]), int(j), int(i)) for i, j in ci)
    vbm, cbm = vbm_candidates[0], cbm_candidates[0]
    gap = cmin - vmax
    scope = str(result.metadata.get("gap_scope", "sampled_path"))
    if gap < -tolerance:
        return BandGapAnalysis("METALLIC", scope, None, "METALLIC", vbm, cbm, vbm_candidates, cbm_candidates,
                               ("Occupied and unoccupied states overlap on the sampled path.",))
    if abs(gap) <= tolerance:
        classification = "ZERO_GAP"
    else:
        if vbm.kpoint is not None and cbm.kpoint is not None:
            delta = np.asarray(vbm.kpoint) - np.asarray(cbm.kpoint)
            direct = bool(np.allclose(delta, np.round(delta), atol=tolerance))
        else:
            direct = vbm.path_sample_index == cbm.path_sample_index
        prefix = "DIRECT" if direct else "INDIRECT"
        classification = f"{prefix}_{'FULL_BZ' if scope == 'full_bz' else 'SAMPLED_PATH'}"
    return BandGapAnalysis("VALID", scope, float(max(0.0, gap)), classification, vbm, cbm,
                           vbm_candidates, cbm_candidates)


def available_fit_directions(result, edge: BandEdge):
    """Return separate path directions; corners are never merged into one fit."""
    bands = _bands(result)
    if bands is None:
        return ()
    count, index = bands.shape[0], edge.path_sample_index
    label = _edge_label(result, index) or f"sample {index}"
    def branch(start, step):
        # A declared high-symmetry point terminates this local direction.  The end point
        # itself remains a valid sample, but no fit can pass through its next corner.
        indices = []
        current = start
        while 0 <= current < count:
            indices.append(current)
            if _edge_label(result, current) is not None:
                break
            current += step
        return tuple(indices)

    directions = []
    if index > 0:
        previous = _edge_label(result, index - 1) or f"sample {index - 1}"
        directions.append(FitDirection(f"{label} → {previous}", branch(index - 1, -1)))
    if index < count - 1:
        following = _edge_label(result, index + 1) or f"sample {index + 1}"
        directions.append(FitDirection(f"{label} → {following}", branch(index + 1, 1)))
    return tuple(directions)


def fit_effective_mass(result, edge: BandEdge, *, points_each_side=5, direction: FitDirection | None = None,
                       carrier="CBM", cell=None, tolerance=TOLERANCE):
    """Fit one user-selected local, physical-k path direction to a quadratic.

    This intentionally does not cross a high-symmetry corner or switch band indices.
    """
    bands = _bands(result)
    carrier = str(carrier).upper()
    if carrier not in {"CBM", "VBM"}:
        return EffectiveMassFit("UNAVAILABLE", carrier, warnings=("Carrier must be CBM or VBM.",))
    if bands is None:
        return EffectiveMassFit("UNAVAILABLE", carrier, warnings=("Band energies are unavailable.",))
    cell = cell if cell is not None else result.metadata.get("cell")
    if cell is None:
        return EffectiveMassFit("UNAVAILABLE", carrier, warnings=("No cell information is available.",))
    try:
        reciprocal = 2.0 * np.pi * np.linalg.inv(np.asarray(cell, dtype=float)).T
    except Exception:
        return EffectiveMassFit("UNAVAILABLE", carrier, warnings=("Cell metadata is invalid.",))
    kpoints = _kpoints(result, bands.shape[0])
    if any(point is None for point in kpoints):
        return EffectiveMassFit("UNAVAILABLE", carrier, warnings=("Physical reciprocal k-points are unavailable.",))
    if not 0 <= edge.path_sample_index < len(kpoints) or not 0 <= edge.band_index < bands.shape[1]:
        return EffectiveMassFit("UNAVAILABLE", carrier, warnings=("Selected band edge is not present in this Result.",))
    if direction is None:
        choices = available_fit_directions(result, edge)
        if not choices:
            return EffectiveMassFit("INSUFFICIENT_POINTS", carrier, warnings=("No continuous sampled path direction is available.",))
        direction = choices[0]
    indices = list(direction.sample_indices[: max(0, int(points_each_side))])
    if len(indices) < 3:
        return EffectiveMassFit("INSUFFICIENT_POINTS", carrier, warnings=("At least three neighboring samples are required in the selected direction.",))
    center = np.asarray(kpoints[edge.path_sample_index], dtype=float)
    distances = np.asarray([np.linalg.norm((np.asarray(kpoints[i]) - center) @ reciprocal) for i in indices], dtype=float)
    energies = np.asarray([bands[i, edge.band_index] for i in indices], dtype=float)
    if np.any(distances <= tolerance):
        return EffectiveMassFit("UNAVAILABLE", carrier, warnings=("Reciprocal-distance samples are degenerate.",))
    coeff = np.polyfit(distances, energies, 2)
    fitted = np.polyval(coeff, distances)
    residual = float(np.sum((energies - fitted) ** 2))
    total = float(np.sum((energies - np.mean(energies)) ** 2))
    r_squared = 1.0 - residual / total if total > 0.0 else 1.0
    curvature = float(2.0 * coeff[0])
    if abs(curvature) <= tolerance:
        return EffectiveMassFit("UNAVAILABLE", carrier, curvature=curvature,
                                warnings=("The selected path has negligible fitted curvature.",))
    hbar, electron_mass, ev_to_joule = 1.054571817e-34, 9.1093837015e-31, 1.602176634e-19
    # curvature here is eV Å²; 1 Å² is 1e-20 m².
    mass_me = abs(hbar * hbar / (curvature * ev_to_joule * 1e-20) / electron_mass)
    warnings = ("Poor parabolic fit — use with caution.",) if r_squared < 0.98 else ()
    return EffectiveMassFit("VALID", carrier, float(mass_me), curvature,
                            tuple(float(value) for value in coeff), r_squared, len(indices),
                            (float(distances.min()), float(distances.max())), direction.label, warnings,
                            tuple(float(value) for value in distances), tuple(float(value) for value in energies),
                            tuple(float(value) for value in fitted), direction.one_sided)


def strain_gap_trend(series, *, tolerance=TOLERANCE):
    """Build a strictly explicit-strain, same-scope derived-gap trend."""
    points, warnings, scope = [], [], None
    for item in series:
        raw = item.metadata.get("strain", item.scientific_result.metadata.get("strain"))
        try:
            strain = float(raw)
        except (TypeError, ValueError):
            warnings.append(f"{item.label}: explicit strain metadata is unavailable.")
            continue
        analysis = analyze_band_edges(item.scientific_result, tolerance=tolerance)
        if analysis.status != "VALID" or analysis.gap is None:
            warnings.append(f"{item.label}: a defensible gap is unavailable.")
            continue
        if scope is None:
            scope = analysis.gap_scope
        if analysis.gap_scope != scope:
            warnings.append(f"{item.label}: gap scope differs from the selected trend.")
            continue
        points.append({"strain_percent": strain, "gap_eV": analysis.gap, "gap_scope": analysis.gap_scope,
                       "directness": analysis.classification, "request_id": item.request_id,
                       "execution_id": item.execution_id, "label": item.label})
    return tuple(sorted(points, key=lambda point: point["strain_percent"])), tuple(warnings)


def derived_comparison_rows(series, *, tolerance=TOLERANCE):
    """Produce display/export-safe derived band rows and a guarded B-A gap delta."""
    rows=[]; analyses=[]
    for item in series:
        analysis=analyze_band_edges(item.scientific_result,tolerance=tolerance)
        analyses.append(analysis)
        scope="Full Brillouin zone" if analysis.gap_scope == "full_bz" else "Sampled path"
        value="Unavailable" if analysis.gap is None else f"{analysis.gap:.6g} eV"
        directness="Unavailable" if analysis.gap is None else analysis.classification.replace("_SAMPLED_PATH", " on sampled path").replace("_FULL_BZ", "").replace("_", " ").title()
        rows.append({"label":item.label,"status":analysis.status,"scope":scope,"gap":value,"gap_eV":analysis.gap,"directness":directness,
                     "vbm":None if analysis.vbm is None else analysis.vbm.energy,"cbm":None if analysis.cbm is None else analysis.cbm.energy,
                     "gap_scope":analysis.gap_scope,"reason":"; ".join(analysis.warnings)})
    delta=None; warning=None
    if len(analyses)==2:
        first,second=analyses
        if first.status==second.status=="VALID" and first.gap is not None and second.gap is not None:
            if first.gap_scope==second.gap_scope:
                delta=second.gap-first.gap
            else:
                warning="Gap difference is not directly comparable because the gap scopes differ."
        elif "METALLIC" in {first.status,second.status}:
            warning="Gap difference is not applicable when a selected Result is metallic."
        else:
            warning="Gap difference is unavailable because one Result lacks defensible occupied/unoccupied metadata."
    return tuple(rows),delta,warning
