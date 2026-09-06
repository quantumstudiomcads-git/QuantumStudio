"""Pb SCDM-erfc parameter provenance and product-contract validation."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import erfc, isfinite
import hashlib
import json


class SCDMContractError(ValueError):
    """Raised when an EPW SCDM request is internally inconsistent."""


@dataclass(frozen=True)
class SCDMParameterFit:
    """Fit provenance for ``p(E)=1/2 erfc((E-mu_fit)/sigma_fit)``.

    Energies and both fitted parameters are absolute eV.  The Pb SCDM
    prescription uses ``mu_scdm = mu_fit - 3*sigma_fit`` while retaining the
    fitted width.
    """

    projectability_source: str
    state_count: int
    energy_min_eV: float
    energy_max_eV: float
    mu_fit_eV: float
    sigma_fit_eV: float
    fit_rmse_eV: float
    fit_r2: float
    fit_method: str = "erfc_nonlinear_least_squares"

    def __post_init__(self) -> None:
        values = (self.energy_min_eV, self.energy_max_eV, self.mu_fit_eV,
                  self.sigma_fit_eV, self.fit_rmse_eV, self.fit_r2)
        if self.state_count < 1 or not all(isfinite(v) for v in values):
            raise SCDMContractError("SCDM fit metadata must be finite and non-empty.")
        if self.energy_min_eV > self.energy_max_eV or self.sigma_fit_eV <= 0:
            raise SCDMContractError("SCDM fit requires ordered energies and sigma > 0.")

    @property
    def mu_scdm_eV(self) -> float:
        return self.mu_fit_eV - 3.0 * self.sigma_fit_eV

    @property
    def sigma_scdm_eV(self) -> float:
        return self.sigma_fit_eV

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.update(mu_scdm_eV=self.mu_scdm_eV, sigma_scdm_eV=self.sigma_scdm_eV)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "SCDMParameterFit":
        if not isinstance(value, dict):
            raise SCDMContractError("SCDM fit provenance must be a mapping.")
        fields = {key: value[key] for key in ("projectability_source", "state_count", "energy_min_eV", "energy_max_eV", "mu_fit_eV", "sigma_fit_eV", "fit_rmse_eV", "fit_r2", "fit_method") if key in value}
        return cls(**fields)

    @property
    def identity(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def erfc_projectability(energy_eV: float, mu_fit_eV: float, sigma_fit_eV: float) -> float:
    """Evaluate the source-audited decreasing erfc projectability model."""
    if not isfinite(sigma_fit_eV) or sigma_fit_eV <= 0:
        raise SCDMContractError("SCDM sigma must be finite and positive.")
    return 0.5 * erfc((energy_eV - mu_fit_eV) / sigma_fit_eV)


def validate_scdm_contract(*, num_wann: int, auto_projections: bool,
                           scdm_proj: bool, entanglement: str,
                           mu_eV: float, sigma_eV: float,
                           manual_projections: bool = False,
                           projectability_disentanglement: bool = False) -> None:
    """Reject mixed SCDM/manual/projectability-disentanglement modes."""
    if num_wann < 1 or not auto_projections or not scdm_proj:
        raise SCDMContractError("SCDM requires positive num_wann, auto_projections, and scdm_proj.")
    if entanglement.lower() != "erfc" or not isfinite(mu_eV) or not isfinite(sigma_eV) or sigma_eV <= 0:
        raise SCDMContractError("SCDM requires erfc entanglement, finite mu, and sigma > 0.")
    if manual_projections or projectability_disentanglement:
        raise SCDMContractError("SCDM cannot be combined with manual projections or projectability disentanglement.")
