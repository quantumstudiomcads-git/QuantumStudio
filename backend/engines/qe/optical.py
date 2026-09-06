"""QE 7.6 epsilon.x independent-particle optical input contract."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from .models import InvalidQEParameterError
from .writer import serialize_namelist


@dataclass(frozen=True)
class OpticalSettings:
    """Serializable user-facing epsilon.x settings; all energies are eV."""

    energy_min_eV: float = 0.0
    energy_max_eV: float = 15.0
    number_of_points: int = 601
    interband_broadening_eV: float = 0.10
    intraband_broadening_eV: float | None = None
    optical_k_mesh: tuple[int, int, int] = (12, 12, 12)
    optical_nbnd: int = 16
    smeartype: str = "gauss"
    requested_directions: tuple[str, ...] = ("xx", "yy", "zz")

    @classmethod
    def from_parameters(cls, parameters: Mapping[str, Any]) -> "OpticalSettings":
        values = dict(parameters or {})
        nested = values.get("optical", {})
        if isinstance(nested, Mapping):
            values = {**values, **nested}
        mesh = values.get("optical_k_mesh", (12, 12, 12))
        directions = values.get("polarization_directions", values.get("requested_directions", ("xx", "yy", "zz")))
        try:
            result = cls(
                energy_min_eV=float(values.get("energy_min_eV", 0.0)),
                energy_max_eV=float(values.get("energy_max_eV", 15.0)),
                number_of_points=int(values.get("number_of_points", 601)),
                interband_broadening_eV=float(values.get("interband_broadening_eV", 0.10)),
                intraband_broadening_eV=(None if values.get("intraband_broadening_eV") in (None, "") else float(values["intraband_broadening_eV"])),
                optical_k_mesh=tuple(int(value) for value in mesh),
                optical_nbnd=int(values.get("optical_nbnd", 16)),
                smeartype=str(values.get("smeartype", "gauss")).strip().lower(),
                requested_directions=tuple(str(value).lower() for value in directions),
            )
        except (TypeError, ValueError) as error:
            raise InvalidQEParameterError("Optical settings contain an invalid numeric value.") from error
        result.validate()
        return result

    def validate(self) -> None:
        if not (isfinite(self.energy_min_eV) and isfinite(self.energy_max_eV) and self.energy_max_eV > self.energy_min_eV):
            raise InvalidQEParameterError("Optical energy_max_eV must be finite and greater than energy_min_eV.")
        if self.number_of_points < 2:
            raise InvalidQEParameterError("Optical number_of_points must be at least two.")
        if not isfinite(self.interband_broadening_eV) or self.interband_broadening_eV <= 0:
            raise InvalidQEParameterError("Optical interband_broadening_eV must be finite and positive.")
        if self.intraband_broadening_eV is not None and (not isfinite(self.intraband_broadening_eV) or self.intraband_broadening_eV < 0):
            raise InvalidQEParameterError("Optical intraband_broadening_eV must be finite and non-negative.")
        if len(self.optical_k_mesh) != 3 or any(value < 1 for value in self.optical_k_mesh):
            raise InvalidQEParameterError("Optical k mesh must contain three positive integers.")
        if self.optical_nbnd < 2:
            raise InvalidQEParameterError("Optical nbnd must include occupied and empty bands.")
        if self.smeartype not in {"gauss", "lorentz"}:
            raise InvalidQEParameterError("QE epsilon.x supports gauss or lorentz spectral broadening.")
        allowed = {"xx", "xy", "xz", "yx", "yy", "yz", "zx", "zy", "zz"}
        if not self.requested_directions or any(value not in allowed for value in self.requested_directions):
            raise InvalidQEParameterError("Optical polarization directions must be Cartesian tensor components.")

    def to_metadata(self) -> dict[str, Any]:
        return {
            "energy_min_eV": self.energy_min_eV,
            "energy_max_eV": self.energy_max_eV,
            "number_of_points": self.number_of_points,
            "interband_broadening_eV": self.interband_broadening_eV,
            "intraband_broadening_eV": self.intraband_broadening_eV,
            "optical_k_mesh": list(self.optical_k_mesh),
            "optical_nbnd": self.optical_nbnd,
            "smeartype": self.smeartype,
            "requested_directions": list(self.requested_directions),
            "scope": "Independent-particle RPA dielectric response (QE epsilon.x dipole approximation); no excitons, BSE, GW, or local-field corrections.",
            "units": {"energy_min_eV": "eV", "energy_max_eV": "eV", "interband_broadening_eV": "eV", "intraband_broadening_eV": "eV"},
        }


def epsilon_input(settings: OpticalSettings, context) -> str:
    """Write QE 7.6 epsilon.x input using its source-defined eV energy grid."""
    settings.validate()
    return "\n\n".join((
        serialize_namelist("INPUTPP", {"prefix": context.prefix, "outdir": context.outdir, "calculation": "eps"}),
        serialize_namelist("ENERGY_GRID", {
            "smeartype": settings.smeartype,
            "intersmear": settings.interband_broadening_eV,
            "intrasmear": 0.0 if settings.intraband_broadening_eV is None else settings.intraband_broadening_eV,
            "nw": settings.number_of_points,
            "wmin": settings.energy_min_eV,
            "wmax": settings.energy_max_eV,
        }),
    )) + "\n"
