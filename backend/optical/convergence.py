"""Serializable optical convergence policies and robust spectrum metrics."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import numpy as np


@dataclass(frozen=True)
class OpticalConvergencePolicy:
    dimensions: tuple[str, ...] = ("K_MESH", "NBND", "INTERBAND_BROADENING", "ENERGY_WINDOW")
    sequences: dict[str, tuple[object, ...]] | None = None
    stop_on_pass: bool = True
    max_steps: int = 4

    def __post_init__(self):
        if self.max_steps < 1 or any(d not in {"K_MESH", "NBND", "INTERBAND_BROADENING", "ENERGY_WINDOW"} for d in self.dimensions):
            raise ValueError("Optical convergence policy contains an invalid dimension or step bound.")

    def to_dict(self):
        value = asdict(self)
        value["dimensions"] = list(self.dimensions)
        if self.sequences is not None:
            value["sequences"] = {key: list(seq) for key, seq in self.sequences.items()}
        return value


def compare_optical_spectra(energy_old, old_epsilon1, old_epsilon2, energy_new, new_epsilon1, new_epsilon2):
    """Compare two spectra on a common axis without unstable pointwise division."""
    old_e, new_e = np.asarray(energy_old, float), np.asarray(energy_new, float)
    axis = new_e if np.array_equal(old_e, new_e) else np.linspace(max(old_e[0], new_e[0]), min(old_e[-1], new_e[-1]), max(2, min(len(old_e), len(new_e))))
    def interp(x, y): return np.interp(axis, np.asarray(x, float), np.asarray(y, float))
    metrics = {}
    for label, old, new in (("epsilon1", interp(old_e, old_epsilon1), interp(new_e, new_epsilon1)), ("epsilon2", interp(old_e, old_epsilon2), interp(new_e, new_epsilon2))):
        denom = max(float(np.linalg.norm(new)), np.finfo(float).eps)
        scale = max(float(np.ptp(new)), np.finfo(float).eps)
        metrics[f"{label}_normalized_l2"] = float(np.linalg.norm(new - old) / denom)
        metrics[f"{label}_normalized_rmse"] = float(np.sqrt(np.mean((new - old) ** 2)) / scale)
    old2, new2 = interp(old_e, old_epsilon2), interp(new_e, new_epsilon2)
    metrics["integrated_epsilon2_relative"] = float(abs(np.trapezoid(new2, axis) - np.trapezoid(old2, axis)) / max(abs(np.trapezoid(new2, axis)), np.finfo(float).eps))
    metrics["dominant_feature_energy_shift_eV"] = float(axis[int(np.argmax(new2))] - axis[int(np.argmax(old2))])
    metrics["dominant_feature_amplitude_relative"] = float(abs(np.max(new2) - np.max(old2)) / max(abs(np.max(new2)), np.finfo(float).eps))
    return metrics
