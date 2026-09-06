"""Typed C5A Wannier90 intent and derived-input errors."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence

class WannierInputError(ValueError): pass

@dataclass(frozen=True)
class WannierInputSettings:
    num_wann: int
    num_bands: int
    projections: tuple[str, ...]
    mp_grid: tuple[int, int, int]
    dis_win_min: float | None = None
    dis_win_max: float | None = None
    dis_froz_min: float | None = None
    dis_froz_max: float | None = None
    num_iter: int | None = None
    dis_num_iter: int | None = None
    spinors: bool = False
    bands_plot: bool = False
    bands_plot_format: str | None = None
    subspace_method: str = "ENERGY_DISENTANGLEMENT"
    auto_projections: bool = False
    scdm_proj: bool = False
    scdm_entanglement: str = ""
    scdm_mu: float | None = None
    scdm_sigma: float | None = None
    use_ws_distance: bool = False

    @classmethod
    def from_parameters(cls, values: Mapping[str, Any]) -> "WannierInputSettings":
        scdm = str(values.get("subspace_method", "")).upper() == "SCDM_ERFC"
        required = ["num_wann", "num_bands"]
        if not scdm:
            required.extend(("projections", "mp_grid"))
        elif "mp_grid" not in values and "nk_coarse" not in values:
            required.append("mp_grid")
        missing = [key for key in required if key not in values]
        if missing:
            raise WannierInputError("Wannierization requires explicit " + ", ".join(missing) + ".")
        projections = values.get("projections", ())
        if isinstance(projections, str): projections = (projections,)
        if not isinstance(projections, Sequence) or (not projections and not scdm) or any(not isinstance(item, str) or not item.strip() for item in projections):
            raise WannierInputError("Wannier projections must be a non-empty list of strings.")
        if scdm and projections:
            raise WannierInputError("SCDM_ERFC cannot be combined with manual projections.")
        if scdm:
            from backend.engines.epw.scdm import validate_scdm_contract
            validate_scdm_contract(num_wann=int(values.get("num_wann", 0)), auto_projections=bool(values.get("auto_projections", False)), scdm_proj=bool(values.get("scdm_proj", False)), entanglement=str(values.get("scdm_entanglement", "")), mu_eV=float(values.get("scdm_mu")), sigma_eV=float(values.get("scdm_sigma")))
        grid = values.get("mp_grid", values.get("nk_coarse"))
        if not isinstance(grid, Sequence) or isinstance(grid, (str, bytes)) or len(grid) != 3:
            raise WannierInputError("Wannier mp_grid must contain three positive integers.")
        try:
            grid = tuple(int(item) for item in grid)
            num_wann, num_bands = int(values["num_wann"]), int(values["num_bands"])
        except (TypeError, ValueError) as error:
            raise WannierInputError("Wannier num_wann, num_bands, and mp_grid must be integers.") from error
        if num_wann < 1 or num_bands < num_wann or any(item < 1 for item in grid):
            raise WannierInputError("Require 1 <= num_wann <= num_bands and positive mp_grid values.")
        kwargs = {key: values.get(key) for key in ("dis_win_min", "dis_win_max", "dis_froz_min", "dis_froz_max", "num_iter", "dis_num_iter", "bands_plot_format")}
        for low, high in (("dis_win_min", "dis_win_max"), ("dis_froz_min", "dis_froz_max")):
            if (kwargs[low] is None) != (kwargs[high] is None):
                raise WannierInputError(f"Wannier {low} and {high} must be supplied together.")
            if kwargs[low] is not None:
                try: kwargs[low], kwargs[high] = float(kwargs[low]), float(kwargs[high])
                except (TypeError, ValueError) as error: raise WannierInputError(f"Wannier {low}/{high} must be numeric.") from error
                if not all(isfinite(item) for item in (kwargs[low], kwargs[high])) or kwargs[low] > kwargs[high]:
                    raise WannierInputError(f"Wannier {low} must not exceed {high}.")
        for key in ("num_iter", "dis_num_iter"):
            if kwargs[key] is not None and int(kwargs[key]) < (1 if key == "num_iter" else 0): raise WannierInputError(f"Wannier {key} must be non-negative." if key == "dis_num_iter" else f"Wannier {key} must be positive.")
            if kwargs[key] is not None: kwargs[key] = int(kwargs[key])
        return cls(num_wann, num_bands, tuple(projections), grid, spinors=bool(values.get("spinors", values.get("soc", False))), bands_plot=bool(values.get("bands_plot", False)), subspace_method=str(values.get("subspace_method", "ENERGY_DISENTANGLEMENT")), auto_projections=bool(values.get("auto_projections", False)), scdm_proj=bool(values.get("scdm_proj", False)), scdm_entanglement=str(values.get("scdm_entanglement", "")), scdm_mu=values.get("scdm_mu"), scdm_sigma=values.get("scdm_sigma"), use_ws_distance=bool(values.get("use_ws_distance", False)), **kwargs)
