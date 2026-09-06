"""Conservative optical unoccupied-band coverage checks."""
from __future__ import annotations
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class OpticalBandCoverage:
    occupied_band_count: int
    nbnd: int
    unoccupied_band_count: int
    requested_max_energy_eV: float
    highest_available_transition_coverage_eV: float | None
    margin_eV: float | None
    adequate: bool
    reason: str = ""

    def to_dict(self):
        return asdict(self)


def assess_band_coverage(*, occupied_band_count, nbnd, requested_max_energy_eV, highest_available_transition_coverage_eV, margin_eV=0.0):
    occupied_band_count, nbnd = int(occupied_band_count), int(nbnd)
    available = float(highest_available_transition_coverage_eV) if highest_available_transition_coverage_eV is not None else None
    margin = None if available is None else available - float(requested_max_energy_eV)
    adequate = available is not None and margin >= float(margin_eV)
    reason = "coverage margin is adequate" if adequate else "OPTICAL_BAND_WINDOW_INADEQUATE: increase nbnd or provide a larger verified transition window"
    return OpticalBandCoverage(occupied_band_count, nbnd, max(0, nbnd - occupied_band_count), float(requested_max_energy_eV), available, margin, adequate, reason)
