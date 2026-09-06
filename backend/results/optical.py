"""Qt-free optical derivations from a parsed complex dielectric spectrum."""
from __future__ import annotations

from math import isfinite
from typing import Mapping

import numpy as np

from .models import ResultStatus, ScientificResult

EV_J = 1.602176634e-19
HBAR_J_S = 1.054571817e-34
C_M_S = 299792458.0
HC_EV_NM = 1239.8419843320026
_DIAGONAL = ("xx", "yy", "zz")


def wavelength_nm(energy_eV):
    energy = np.asarray(energy_eV, dtype=float)
    if np.any(~np.isfinite(energy)) or np.any(energy <= 0):
        raise ValueError("Wavelength conversion requires finite positive photon energies.")
    return HC_EV_NM / energy


def _component_values(epsilon1, epsilon2):
    first = np.asarray(epsilon1, dtype=float)
    second = np.asarray(epsilon2, dtype=float)
    if first.shape != second.shape or first.ndim != 1 or len(first) < 2:
        raise ValueError("Dielectric components must be same-length one-dimensional spectra.")
    if not (np.all(np.isfinite(first)) and np.all(np.isfinite(second))):
        raise ValueError("Dielectric components must be finite.")
    modulus = np.hypot(first, second)
    n_argument = (modulus + first) / 2.0
    k_argument = (modulus - first) / 2.0
    # These arguments are non-negative analytically.  Clip only floating point
    # underflow close to zero and expose material violations to the caller.
    tolerance = 1.0e-12 * np.maximum(1.0, modulus)
    if np.any(n_argument < -tolerance) or np.any(k_argument < -tolerance):
        raise ValueError("Complex dielectric input violates the principal-index branch contract.")
    n = np.sqrt(np.maximum(n_argument, 0.0))
    kappa = np.sqrt(np.maximum(k_argument, 0.0))
    denominator = (n + 1.0) ** 2 + kappa ** 2
    reflectivity = ((n - 1.0) ** 2 + kappa ** 2) / denominator
    epsilon_norm = first ** 2 + second ** 2
    loss = np.divide(second, epsilon_norm, out=np.zeros_like(second), where=epsilon_norm > np.finfo(float).tiny)
    return n, kappa, reflectivity, loss


def derive_optical_arrays(energy_eV, components: Mapping[str, tuple[object, object]]):
    """Derive n, κ, α, R and -Im(1/ε) from ε=ε1+iε2 for diagonal components."""
    energy = np.asarray(energy_eV, dtype=float)
    if energy.ndim != 1 or len(energy) < 2 or not np.all(np.isfinite(energy)) or not np.all(np.diff(energy) > 0):
        raise ValueError("Optical photon energy axis must be finite and strictly increasing.")
    if np.any(energy < 0):
        raise ValueError("Optical photon energy cannot be negative.")
    omega = energy * EV_J / HBAR_J_S
    arrays = {"energy_eV": energy}
    for direction in _DIAGONAL:
        try:
            epsilon1, epsilon2 = components[direction]
        except KeyError as error:
            raise ValueError(f"Missing diagonal dielectric component {direction}.") from error
        n, kappa, reflectivity, loss = _component_values(epsilon1, epsilon2)
        alpha_cm1 = 2.0 * omega * kappa / C_M_S * 1.0e-2
        arrays.update({
            f"refractive_index_{direction}": n,
            f"extinction_coefficient_{direction}": kappa,
            f"absorption_coefficient_cm1_{direction}": alpha_cm1,
            f"reflectivity_{direction}": reflectivity,
            f"loss_function_{direction}": loss,
        })
    return arrays


def derive_optical_properties(dielectric: ScientificResult) -> ScientificResult:
    if dielectric.result_type != "OpticalDielectricResult":
        raise ValueError("Derived optical quantities require an OpticalDielectricResult.")
    energy = dielectric.arrays.get("energy_eV")
    components = {
        direction: (dielectric.arrays[f"epsilon1_{direction}"], dielectric.arrays[f"epsilon2_{direction}"])
        for direction in _DIAGONAL
    }
    arrays = derive_optical_arrays(energy, components)
    metadata = {
        "source_dielectric_result_id": dielectric.result_id,
        "epsilon_convention": "epsilon(E) = epsilon1(E) + i epsilon2(E)",
        "normal_incidence_assumption": "vacuum/material interface at normal incidence",
        "absorption_definition": "alpha = 2 omega kappa / c; energy E converted from eV to omega = E/hbar; exported in cm^-1",
        "loss_definition": "-Im[1/epsilon] = epsilon2/(epsilon1^2 + epsilon2^2)",
        "units": {
            "energy_eV": "eV", "refractive_index": "dimensionless", "extinction_coefficient": "dimensionless",
            "absorption_coefficient_cm1": "cm^-1", "reflectivity": "dimensionless", "loss_function": "dimensionless",
        },
        "parent_dielectric_provenance": dielectric.provenance.__dict__,
    }
    warnings = list(dielectric.warnings)
    if bool(dielectric.metadata.get("two_dimensional_supercell", False)):
        warnings.append("Raw supercell dielectric response for a vacuum-containing 2D cell is retained; it is not a vacuum-normalized 2D material dielectric constant.")
    return ScientificResult("OpticalPropertiesResult", dielectric.status, dielectric.provenance, arrays=arrays, metadata=metadata, warnings=warnings)
