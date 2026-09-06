"""Shared derived optical observables, including explicitly SI conductivity."""
from __future__ import annotations

import numpy as np

EPSILON_0_F_M = 8.8541878128e-12


def optical_conductivity(energy_eV, epsilon1, epsilon2, *, time_convention="exp(-i omega t)"):
    """Return (sigma1, sigma2) in S/m for epsilon=epsilon1+i epsilon2.

    The sign is tied to the stored ``exp(-i omega t)`` convention.  At zero
    photon energy the conductivity is defined as zero for this interband
    response because omega=0 makes the dielectric-to-conductivity transform
    singular without a separately modelled Drude term.
    """
    if time_convention != "exp(-i omega t)":
        raise ValueError("Optical conductivity requires the audited exp(-i omega t) convention.")
    energy = np.asarray(energy_eV, dtype=float)
    real = np.asarray(epsilon1, dtype=float)
    imag = np.asarray(epsilon2, dtype=float)
    if energy.shape != real.shape or real.shape != imag.shape or np.any(~np.isfinite(energy + real + imag)):
        raise ValueError("Conductivity inputs must be finite arrays with matching shapes.")
    omega = energy * 1.602176634e-19 / 1.054571817e-34
    sigma1 = EPSILON_0_F_M * omega * imag
    sigma2 = -EPSILON_0_F_M * omega * (real - 1.0)
    return sigma1, sigma2


def dimensionality_warning(dimensionality):
    if str(dimensionality) in {"SLAB_2D_SUPERCELL", "Dimensionality.SLAB_2D_SUPERCELL"}:
        return "2D_SUPERCELL_NORMALIZATION"
    return None
