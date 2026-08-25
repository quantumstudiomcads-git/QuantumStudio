"""Validated, execution-free BoltzTraP2 workflow settings for C5C."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any


class BTP2SettingsError(ValueError):
    pass


class RelaxationTimeModel(str, Enum):
    UNSPECIFIED_RELAXATION_TIME = "UNSPECIFIED_RELAXATION_TIME"
    CONSTANT_RELAXATION_TIME = "CONSTANT_RELAXATION_TIME"
    EPW_SCATTERING_TIME = "EPW_SCATTERING_TIME"  # Reserved; not implemented in C5C.


def _positive_mesh(value: object, name: str) -> tuple[int, int, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise BTP2SettingsError(f"{name} must contain three positive integers.")
    try:
        result = tuple(int(item) for item in value)
    except (TypeError, ValueError) as error:
        raise BTP2SettingsError(f"{name} must contain three positive integers.") from error
    if any(item < 1 or item != source for item, source in zip(result, value)):
        raise BTP2SettingsError(f"{name} must contain three positive integers.")
    return result


def _numbers(value: object, name: str, *, positive: bool = False) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise BTP2SettingsError(f"{name} must be a non-empty numeric list.")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError) as error:
        raise BTP2SettingsError(f"{name} must be a non-empty numeric list.") from error
    if not all(isfinite(item) and (item > 0 if positive else True) for item in result):
        raise BTP2SettingsError(f"{name} values must be finite" + (" and positive." if positive else "."))
    return result


def _range(value: object, name: str, *, positive: bool = False) -> tuple[float, float, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise BTP2SettingsError(f"{name} must be [minimum, maximum, count].")
    try:
        low, high, count = float(value[0]), float(value[1]), int(value[2])
    except (TypeError, ValueError) as error:
        raise BTP2SettingsError(f"{name} must be [minimum, maximum, count].") from error
    if not isfinite(low) or not isfinite(high) or low > high or count < 1 or (positive and low < 0):
        raise BTP2SettingsError(f"{name} has an invalid range.")
    return low, high, count


@dataclass(frozen=True)
class BoltzTraP2Settings:
    transport_k_mesh: tuple[int, int, int]
    num_bands: int
    temperatures: tuple[float, ...] = ()
    chemical_potentials: tuple[float, ...] = ()  # eV, relative to the declared reference energy.
    chemical_potential_range: tuple[float, float, int] | None = None  # eV
    carrier_concentrations: tuple[float, ...] = ()  # cm^-3; distinct from chemical potential.
    carrier_concentration_range: tuple[float, float, int] | None = None  # cm^-3
    interpolation: dict[str, Any] = None
    relaxation_time_model: RelaxationTimeModel = RelaxationTimeModel.UNSPECIFIED_RELAXATION_TIME
    relaxation_time: float | None = None  # seconds
    effective_thickness: float | None = None  # angstrom, explicit only for 2D absolute normalization.
    spin: bool = False
    soc: bool = False

    @classmethod
    def from_parameters(cls, values: Mapping[str, Any], *, require_transport: bool) -> "BoltzTraP2Settings":
        missing = [name for name in ("transport_k_mesh", "num_bands") if name not in values]
        if missing:
            raise BTP2SettingsError("BoltzTraP2 requires explicit " + ", ".join(missing) + ".")
        mesh = _positive_mesh(values["transport_k_mesh"], "transport_k_mesh")
        try:
            bands = int(values["num_bands"])
        except (TypeError, ValueError) as error:
            raise BTP2SettingsError("num_bands must be a positive integer.") from error
        if bands < 1 or bands != values["num_bands"]:
            raise BTP2SettingsError("num_bands must be a positive integer.")
        temperatures = _numbers(values.get("temperatures", ()), "temperatures", positive=True) if "temperatures" in values else ()
        chemical_potentials = _numbers(values.get("chemical_potentials", ()), "chemical_potentials") if "chemical_potentials" in values else ()
        chemical_range = _range(values["chemical_potential_range"], "chemical_potential_range") if "chemical_potential_range" in values else None
        if chemical_potentials and chemical_range is not None:
            raise BTP2SettingsError("Specify either chemical_potentials or chemical_potential_range, not both.")
        if require_transport and (not temperatures or (not chemical_potentials and chemical_range is None)):
            raise BTP2SettingsError("Transport integration requires explicit temperatures and chemical_potentials or chemical_potential_range.")
        carriers = _numbers(values.get("carrier_concentrations", ()), "carrier_concentrations", positive=True) if "carrier_concentrations" in values else ()
        carrier_range = _range(values["carrier_concentration_range"], "carrier_concentration_range", positive=True) if "carrier_concentration_range" in values else None
        if carriers and carrier_range is not None:
            raise BTP2SettingsError("Specify either carrier_concentrations or carrier_concentration_range, not both.")
        interpolation = values.get("interpolation", {})
        if not isinstance(interpolation, Mapping):
            raise BTP2SettingsError("interpolation must be a JSON object of deterministic controls.")
        try:
            model = RelaxationTimeModel(str(values.get("relaxation_time_model", RelaxationTimeModel.UNSPECIFIED_RELAXATION_TIME.value)))
        except ValueError as error:
            raise BTP2SettingsError("Unsupported relaxation_time_model.") from error
        if model is RelaxationTimeModel.EPW_SCATTERING_TIME:
            raise BTP2SettingsError("EPW_SCATTERING_TIME is reserved for a future EPW lifetime integration.")
        tau = values.get("relaxation_time")
        if model is RelaxationTimeModel.CONSTANT_RELAXATION_TIME:
            try: tau = float(tau)
            except (TypeError, ValueError) as error: raise BTP2SettingsError("CONSTANT_RELAXATION_TIME requires relaxation_time in seconds.") from error
            if not isfinite(tau) or tau <= 0: raise BTP2SettingsError("relaxation_time must be finite and > 0 seconds.")
        elif tau is not None:
            raise BTP2SettingsError("relaxation_time is allowed only with CONSTANT_RELAXATION_TIME.")
        thickness = values.get("effective_thickness")
        if thickness is not None:
            try: thickness = float(thickness)
            except (TypeError, ValueError) as error: raise BTP2SettingsError("effective_thickness must be a positive value in angstrom.") from error
            if not isfinite(thickness) or thickness <= 0: raise BTP2SettingsError("effective_thickness must be a positive value in angstrom.")
        return cls(mesh, bands, temperatures, chemical_potentials, chemical_range, carriers, carrier_range, dict(interpolation), model, tau, thickness, bool(values.get("spin", False)), bool(values.get("soc", False)))

    def to_dict(self) -> dict[str, Any]:
        return {"transport_k_mesh": list(self.transport_k_mesh), "num_bands": self.num_bands, "temperatures_kelvin": list(self.temperatures), "chemical_potentials_ev": list(self.chemical_potentials), "chemical_potential_range_ev": list(self.chemical_potential_range) if self.chemical_potential_range else None, "carrier_concentrations_cm3": list(self.carrier_concentrations), "carrier_concentration_range_cm3": list(self.carrier_concentration_range) if self.carrier_concentration_range else None, "interpolation": dict(self.interpolation or {}), "relaxation_time_model": self.relaxation_time_model.value, "relaxation_time_seconds": self.relaxation_time, "effective_thickness_angstrom": self.effective_thickness, "spin": self.spin, "soc": self.soc}
