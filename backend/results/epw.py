"""Qt-free parsers and invariants for native EPW 6.1 observables.

EPW writes the isotropic ``.a2f`` table in meV.  The first column is the
phonon energy and the following columns are alpha2F values for the requested
phonon smearings; the cumulative columns are emitted after the table.  This
module deliberately parses only self-describing numeric tables and never
turns a missing/ambiguous EPW file into a valid scientific result.
"""
from __future__ import annotations

import re
import itertools
from pathlib import Path
import numpy as np


class EPWParseError(ValueError):
    pass


def _numbers(line: str) -> list[float]:
    return [float(x.replace("D", "E").replace("d", "e")) for x in re.findall(
        r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][-+]?\d+)?", line
    )]


def integrate_lambda(frequency_mev, alpha2f, *, zero_tolerance=1.0e-14) -> float:
    """Return ``2 integral alpha2F(w)/w dw`` using EPW's energy coordinate."""
    w = np.asarray(frequency_mev, dtype=float)
    a = np.asarray(alpha2f, dtype=float)
    if w.ndim != 1 or a.ndim != 1 or w.shape != a.shape or len(w) < 2:
        raise EPWParseError("alpha2F frequency and value arrays must be equal one-dimensional arrays.")
    if not np.all(np.isfinite(w)) or not np.all(np.isfinite(a)) or np.any(np.diff(w) < 0):
        raise EPWParseError("alpha2F contains non-finite or non-monotone data.")
    integrand = np.zeros_like(a)
    positive = np.abs(w) > zero_tolerance
    integrand[positive] = a[positive] / w[positive]
    return float(2.0 * np.trapezoid(integrand, w))


def parse_a2f(path: str | Path):
    """Parse the formatted EPW 6.1 ``prefix.a2f`` contract.

    EPW's normal single-smearing table starts with ``w[meV] a2f``.  For a
    multi-smearing table, the first numeric column remains meV and each next
    column is one alpha2F series.  The parser preserves all series and does
    not guess which one is canonical.
    """
    source = Path(path)
    if not source.is_file():
        raise EPWParseError(f"EPW alpha2F file is missing: {source}")
    rows = []
    header = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.lower().startswith(("w[", "integrated", "phonon smearing", "electron smearing", "fermi window", "summed", "lambda_int", "lambda_sum")):
            header.append(stripped)
            continue
        try:
            values = _numbers(stripped)
        except ValueError:
            continue
        if len(values) >= 2:
            rows.append(values)
    if len(rows) < 2:
        raise EPWParseError("EPW alpha2F file contains fewer than two numeric rows.")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise EPWParseError("EPW alpha2F numeric rows have inconsistent column counts.")
    data = np.asarray(rows, dtype=float)
    if not np.all(np.isfinite(data)) or np.any(np.diff(data[:, 0]) < 0):
        raise EPWParseError("EPW alpha2F table contains invalid frequency data.")
    return {"frequency_mev": data[:, 0], "alpha2f": data[:, 1:], "header": tuple(header), "unit": "meV"}


def parse_tc_eigenvalues(path: str | Path):
    """Parse a simple EPW temperature/eigenvalue table without extrapolation."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        values = _numbers(line)
        if len(values) >= 2:
            rows.append(values[:2])
    if len(rows) < 2:
        raise EPWParseError("No temperature/eigenvalue table was found.")
    data = np.asarray(rows, dtype=float)
    if not np.all(np.isfinite(data)) or np.any(np.diff(data[:, 0]) <= 0):
        raise EPWParseError("Temperature/eigenvalue data are invalid or non-monotone.")
    crossings = []
    for (t0, e0), (t1, e1) in zip(data[:-1], data[1:]):
        if (e0 - 1.0) * (e1 - 1.0) <= 0 and e0 != e1:
            crossings.append((float(t0), float(t1), float(e0), float(e1)))
    if len(crossings) != 1:
        raise EPWParseError("Tc crossing is absent or ambiguous; no extrapolated Tc is returned.")
    t0, t1, e0, e1 = crossings[0]
    tc = t0 + (1.0 - e0) * (t1 - t0) / (e1 - e0)
    return {"temperature_K": data[:, 0], "eigenvalue": data[:, 1], "bracket": crossings[0], "tc_K": float(tc)}


def parse_wannier_band_blocks(path: str | Path, *, expected_kpoints: int | None = None):
    """Parse Wannier90/EPW bands_plot two-column band blocks.

    The formatted file is one (path_distance, energy) block per band,
    separated by blank lines. It is not a row-wise multi-band table.
    """
    source = Path(path)
    if not source.is_file():
        raise EPWParseError(f"Wannier band file is missing: {source}")
    blocks = []
    current = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        values = _numbers(line)
        if len(values) >= 2:
            current.append((values[0], values[1]))
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    if not blocks or any(len(block) == 0 for block in blocks):
        raise EPWParseError("Wannier band file has no complete band blocks.")
    widths = {len(block) for block in blocks}
    if len(widths) != 1:
        raise EPWParseError("Wannier band blocks have inconsistent k-point counts.")
    nk = widths.pop()
    if expected_kpoints is not None and nk != expected_kpoints:
        raise EPWParseError(f"Wannier band file has {nk} points, expected {expected_kpoints}.")
    distances = np.asarray([row[0] for row in blocks[0]], dtype=float)
    energies = np.asarray([[row[1] for row in block] for block in blocks], dtype=float).T
    if not np.all(np.isfinite(distances)) or not np.all(np.isfinite(energies)):
        raise EPWParseError("Wannier band file contains non-finite values.")
    if np.any(np.diff(distances) < 0):
        raise EPWParseError("Wannier path distances are not monotone.")
    return {"distance": distances, "energies": energies, "shape": energies.shape}


def parse_qe_band_blocks(path: str | Path, *, expected_bands: int | None = None,
                         expected_kpoints: int | None = None):
    """Parse bands.x plottable output into (kpoint, band) energies."""
    source = Path(path)
    if not source.is_file():
        raise EPWParseError(f"QE band file is missing: {source}")
    text = source.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"nbnd\s*=\s*(\d+)\s*,\s*nks\s*=\s*(\d+)", text, re.I)
    if not match:
        raise EPWParseError("QE band header with nbnd and nks is missing.")
    nbnd, nks = map(int, match.groups())
    if expected_bands is not None and nbnd != expected_bands:
        raise EPWParseError(f"QE band file has {nbnd} bands, expected {expected_bands}.")
    if expected_kpoints is not None and nks != expected_kpoints:
        raise EPWParseError(f"QE band file has {nks} points, expected {expected_kpoints}.")
    values = []
    for line in text.splitlines():
        numbers = _numbers(line)
        if len(numbers) >= nbnd:
            values.append(numbers[:nbnd])
    if len(values) != nks:
        raise EPWParseError(f"QE band file contains {len(values)} energy rows, expected {nks}.")
    energies = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(energies)):
        raise EPWParseError("QE band file contains non-finite energies.")
    return {"energies": energies, "nbnd": nbnd, "nks": nks}


def _band_error_metrics(errors):
    array = np.asarray(errors, dtype=float).ravel()
    if array.size == 0:
        return {"count": 0}
    return {
        "count": int(array.size),
        "max_eV": float(np.max(array)),
        "rms_eV": float(np.sqrt(np.mean(array * array))),
        "mean_eV": float(np.mean(array)),
        "p95_eV": float(np.percentile(array, 95)),
    }



def fermi_crossings(energies, *, fermi_energy: float, distances=None, path_segments=None):
    """Return linear Fermi crossings for a band array, without branch relabelling."""
    values = np.asarray(energies, dtype=float)
    if values.ndim != 2 or not np.all(np.isfinite(values)):
        raise EPWParseError("Fermi-crossing input must be a finite (k-point, band) array.")
    nk = values.shape[0]
    axis = np.arange(nk, dtype=float) if distances is None else np.asarray(distances, dtype=float)
    if axis.shape != (nk,) or not np.all(np.isfinite(axis)):
        raise EPWParseError("Fermi-crossing distances must match the k-point axis.")
    result = []
    for band in range(values.shape[1]):
        for ik in range(nk - 1):
            left, right = values[ik, band] - fermi_energy, values[ik + 1, band] - fermi_energy
            if left == 0.0:
                fraction = 0.0
            elif left * right < 0.0:
                fraction = float(-left / (right - left))
            else:
                continue
            segment = None
            if path_segments:
                for name, start, end in path_segments:
                    if int(start) <= ik <= int(end):
                        segment = str(name)
                        break
            result.append({
                "band": band,
                "between_indices": (ik, ik + 1),
                "fraction": fraction,
                "path_distance": float(axis[ik] + fraction * (axis[ik + 1] - axis[ik])),
                "segment": segment,
            })
    return tuple(result)

def match_wannier_bands(direct_energies, wannier_energies, *, fermi_energy: float,
                        candidate_indices, path_segments=None, energy_window_eV: float = 2.0):
    """Compare a Wannier subspace to direct bands with one-to-one matching."""
    direct = np.asarray(direct_energies, dtype=float)
    wannier = np.asarray(wannier_energies, dtype=float)
    candidates = tuple(int(i) for i in candidate_indices)
    if direct.ndim != 2 or wannier.ndim != 2 or direct.shape[0] != wannier.shape[0]:
        raise EPWParseError("Direct and Wannier band arrays must share the k-point axis.")
    if not candidates or any(i < 0 or i >= direct.shape[1] for i in candidates):
        raise EPWParseError("Direct-band candidate indices are invalid.")
    if len(candidates) < wannier.shape[1]:
        raise EPWParseError("Fewer direct candidates than Wannier bands.")
    errors = np.empty_like(wannier)
    assignments = []
    for ik in range(direct.shape[0]):
        best = min(
            ((float(np.sum((direct[ik, list(perm)] - wannier[ik]) ** 2)), perm)
             for perm in itertools.permutations(candidates, wannier.shape[1])),
            key=lambda item: item[0],
        )
        perm = best[1]
        assignments.append(perm)
        errors[ik] = np.abs(direct[ik, list(perm)] - wannier[ik])
    if energy_window_eV <= 0:
        raise EPWParseError("Wannier comparison energy window must be positive.")
    window = np.any(np.abs(direct[:, candidates] - fermi_energy) <= energy_window_eV, axis=1)
    window |= np.any(np.abs(wannier - fermi_energy) <= energy_window_eV, axis=1)
    segments = {}
    if path_segments:
        for name, start, end in path_segments:
            segments[str(name)] = _band_error_metrics(errors[int(start):int(end) + 1])
    return {
        "errors": errors,
        "assignments": tuple(assignments),
        "all": _band_error_metrics(errors),
        "fermi_window": _band_error_metrics(errors[window]) if np.any(window) else {"count": 0},
        "energy_window_eV": float(energy_window_eV),
        "segments": segments,
    }


def parse_wannier_hr(path: str | Path):
    """Parse a Wannier90 hr.dat file, retaining R degeneracies and matrix rows."""
    source = Path(path)
    if not source.is_file():
        raise EPWParseError(f"Wannier Hamiltonian is missing: {source}")
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        nw = int(lines[1].strip())
        nr = int(lines[2].strip())
    except (IndexError, ValueError) as exc:
        raise EPWParseError("Wannier hr.dat header is malformed.") from exc
    degeneracies, index = [], 3
    while len(degeneracies) < nr and index < len(lines):
        degeneracies.extend(int(value) for value in lines[index].split())
        index += 1
    if len(degeneracies) != nr or any(value <= 0 for value in degeneracies):
        raise EPWParseError("Wannier hr.dat degeneracy table is malformed.")
    rows = []
    for line in lines[index:]:
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 7:
            raise EPWParseError("Wannier hr.dat matrix row is malformed.")
        rows.append((tuple(int(value) for value in fields[:3]), int(fields[3]) - 1,
                     int(fields[4]) - 1, complex(float(fields[5]), float(fields[6]))))
    if len(rows) != nr * nw * nw:
        raise EPWParseError(f"Wannier hr.dat has {len(rows)} matrix rows, expected {nr * nw * nw}.")
    return {"num_wann": nw, "num_rpts": nr, "degeneracies": tuple(degeneracies), "rows": tuple(rows)}


def evaluate_wannier_hr(table, fractional_kpoints):
    """Evaluate a Wannier90 Hamiltonian at fractional reciprocal k points."""
    import numpy as _np
    kpoints = _np.asarray(fractional_kpoints, dtype=float)
    if kpoints.ndim != 2 or kpoints.shape[1] != 3:
        raise EPWParseError("Fractional k points must have shape (N, 3).")
    nw, nr = int(table["num_wann"]), int(table["num_rpts"])
    rows, degeneracies = table["rows"], table["degeneracies"]
    r_vectors = tuple(dict.fromkeys(row[0] for row in rows))
    if len(r_vectors) != nr:
        raise EPWParseError("Wannier hr.dat R-point count does not match its header.")
    result = _np.empty((len(kpoints), nw), dtype=float)
    for ik, kpoint in enumerate(kpoints):
        matrix = _np.zeros((nw, nw), dtype=complex)
        for ir, r_vector in enumerate(r_vectors):
            phase = _np.exp(2j * _np.pi * _np.dot(r_vector, kpoint)) / degeneracies[ir]
            for row in rows:
                if row[0] == r_vector:
                    matrix[row[1], row[2]] += phase * row[3]
        result[ik] = _np.linalg.eigvalsh((matrix + matrix.conj().T) / 2).real
    return result
