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

    @classmethod
    def from_parameters(cls, values: Mapping[str, Any]) -> "WannierInputSettings":
        missing = [key for key in ("num_wann", "num_bands", "projections", "mp_grid") if key not in values]
        if missing:
            raise WannierInputError("Wannierization requires explicit " + ", ".join(missing) + ".")
        projections = values["projections"]
        if isinstance(projections, str): projections = (projections,)
        if not isinstance(projections, Sequence) or not projections or any(not isinstance(item, str) or not item.strip() for item in projections):
            raise WannierInputError("Wannier projections must be a non-empty list of strings.")
        grid = values["mp_grid"]
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
            if kwargs[key] is not None and int(kwargs[key]) < 1: raise WannierInputError(f"Wannier {key} must be positive.")
            if kwargs[key] is not None: kwargs[key] = int(kwargs[key])
        return cls(num_wann, num_bands, tuple(projections), grid, spinors=bool(values.get("spinors", values.get("soc", False))), bands_plot=bool(values.get("bands_plot", False)), **kwargs)
