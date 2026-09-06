"""Serializable, engine-neutral optical workflow contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


class _Values(str, Enum):
    def __str__(self):
        return self.value


class ResponseModel(_Values):
    INDEPENDENT_PARTICLE_DIELECTRIC = "INDEPENDENT_PARTICLE_DIELECTRIC"
    TDDFT = "TDDFT"
    GW_RPA = "GW_RPA"
    BSE = "BSE"
    REAL_TIME_TDDFT = "REAL_TIME_TDDFT"


class CarrierRegime(_Values):
    SEMICONDUCTOR = "SEMICONDUCTOR"
    INSULATOR = "INSULATOR"
    METAL = "METAL"
    UNKNOWN = "UNKNOWN"


class Dimensionality(_Values):
    BULK_3D = "BULK_3D"
    SLAB_2D_SUPERCELL = "SLAB_2D_SUPERCELL"
    WIRE_1D_SUPERCELL = "WIRE_1D_SUPERCELL"
    MOLECULE_0D_SUPERCELL = "MOLECULE_0D_SUPERCELL"


class BandWindowPolicy(_Values):
    AUTO = "AUTO"
    EXPLICIT_NBND = "EXPLICIT_NBND"
    INHERIT_IF_ADEQUATE = "INHERIT_IF_ADEQUATE"


class OpticalRoute(_Values):
    BULK_INTERBAND = "BULK_INTERBAND"
    BULK_METALLIC = "BULK_METALLIC"
    SLAB_SUPERCELL_RAW = "SLAB_SUPERCELL_RAW"
    SPIN_POLARIZED = "SPIN_POLARIZED"
    SOC_NONCOLLINEAR = "SOC_NONCOLLINEAR"


@dataclass(frozen=True)
class OpticalCalculationSpecification:
    response_model: ResponseModel = ResponseModel.INDEPENDENT_PARTICLE_DIELECTRIC
    energy_min_eV: float = 0.0
    energy_max_eV: float = 15.0
    energy_points: int = 601
    interband_broadening_eV: float = 0.10
    intraband_broadening_eV: float | None = None
    requested_tensor_components: tuple[str, ...] = ("xx", "yy", "zz")
    requested_derived_properties: tuple[str, ...] = ("refractive_index", "extinction_coefficient", "absorption", "reflectivity", "loss")
    carrier_regime: CarrierRegime = CarrierRegime.SEMICONDUCTOR
    dimensionality: Dimensionality = Dimensionality.BULK_3D
    band_window_policy: BandWindowPolicy = BandWindowPolicy.AUTO
    k_mesh_policy: str = "INTERMEDIATE"
    precision_policy: str = "INTERMEDIATE"
    optical_k_mesh: tuple[int, int, int] = (12, 12, 12)
    optical_nbnd: int | None = None
    soc: bool = False
    noncollinear: bool = False
    spin_polarized: bool = False
    dft_plus_u: bool = False
    hybrid_functional: bool = False

    def __post_init__(self):
        if self.energy_max_eV <= self.energy_min_eV or self.energy_points < 2:
            raise ValueError("Optical energy range must increase and contain at least two points.")
        if self.interband_broadening_eV <= 0 or (self.intraband_broadening_eV is not None and self.intraband_broadening_eV < 0):
            raise ValueError("Optical broadenings must be positive/non-negative.")
        if len(self.optical_k_mesh) != 3 or any(int(n) != n or int(n) < 1 for n in self.optical_k_mesh):
            raise ValueError("Optical k mesh must contain three positive integers.")
        if self.noncollinear and not self.soc:
            raise ValueError("A noncollinear optical state must declare SOC or an explicit engine state.")

    def to_dict(self):
        value = asdict(self)
        for key in ("response_model", "carrier_regime", "dimensionality", "band_window_policy"):
            value[key] = value[key].value
        value["optical_k_mesh"] = list(self.optical_k_mesh)
        value["requested_tensor_components"] = list(self.requested_tensor_components)
        value["requested_derived_properties"] = list(self.requested_derived_properties)
        return value

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]):
        values = dict(data)
        for key, enum_type in (("response_model", ResponseModel), ("carrier_regime", CarrierRegime), ("dimensionality", Dimensionality), ("band_window_policy", BandWindowPolicy)):
            if key in values and not isinstance(values[key], enum_type):
                values[key] = enum_type(values[key])
        for key in ("optical_k_mesh", "requested_tensor_components", "requested_derived_properties"):
            if key in values:
                values[key] = tuple(values[key])
        values = {key: value for key, value in values.items() if key in cls.__dataclass_fields__}
        return cls(**values)


@dataclass(frozen=True)
class SystemCharacterization:
    periodicity: tuple[bool, bool, bool] = (True, True, True)
    dimensionality: Dimensionality = Dimensionality.BULK_3D
    carrier_regime: CarrierRegime = CarrierRegime.UNKNOWN
    spin_polarized: bool = False
    noncollinear: bool = False
    soc: bool = False
    dft_plus_u: bool = False
    hybrid_functional: bool = False
    occupations: str = "fixed"
    scf_smearing: str | None = None
    scf_degauss: float | None = None


@dataclass(frozen=True)
class OpticalCapabilityMatrix:
    bulk_semiconductor: str = "SUPPORTED"
    bulk_metal: str = "UNVERIFIED"
    spin_polarized: str = "UNVERIFIED"
    soc_noncollinear: str = "UNVERIFIED"
    dft_plus_u: str = "UNVERIFIED"
    hybrid: str = "UNSUPPORTED"
    slab_raw_supercell: str = "SUPPORTED"
    off_diagonal_tensor: str = "UNVERIFIED"
    optical_conductivity_derived: str = "IMPLEMENTED_UNVALIDATED"


class OpticalWorkflowRouter:
    """Select a scientific route and reject combinations the engine cannot claim."""

    def __init__(self, capabilities: OpticalCapabilityMatrix | None = None):
        self.capabilities = capabilities or OpticalCapabilityMatrix()

    def route(self, specification: OpticalCalculationSpecification, system: SystemCharacterization, *, engine_id="quantum_espresso"):
        if specification.response_model is not ResponseModel.INDEPENDENT_PARTICLE_DIELECTRIC:
            raise ValueError(f"QE epsilon.x does not implement response model {specification.response_model.value}.")
        if specification.hybrid_functional or system.hybrid_functional:
            raise ValueError("UNSUPPORTED_ENGINE_COMBINATION: hybrid optical response is not validated for epsilon.x.")
        if specification.noncollinear or specification.soc or system.noncollinear or system.soc:
            if self.capabilities.soc_noncollinear not in {"SUPPORTED", "SUPPORTED_EXPENSIVE"}:
                raise ValueError("UNSUPPORTED_ENGINE_COMBINATION: SOC/noncollinear epsilon.x route is unverified.")
            route = OpticalRoute.SOC_NONCOLLINEAR
        elif specification.spin_polarized or system.spin_polarized:
            if self.capabilities.spin_polarized != "SUPPORTED":
                raise ValueError("UNSUPPORTED_ENGINE_COMBINATION: spin-polarized epsilon.x route is unverified.")
            route = OpticalRoute.SPIN_POLARIZED
        elif specification.dimensionality is Dimensionality.SLAB_2D_SUPERCELL or system.dimensionality is Dimensionality.SLAB_2D_SUPERCELL:
            route = OpticalRoute.SLAB_SUPERCELL_RAW
        elif specification.carrier_regime is CarrierRegime.METAL or system.carrier_regime is CarrierRegime.METAL:
            if self.capabilities.bulk_metal != "SUPPORTED":
                raise ValueError("UNSUPPORTED_ENGINE_COMBINATION: metallic epsilon.x controls are not validated.")
            route = OpticalRoute.BULK_METALLIC
        else:
            route = OpticalRoute.BULK_INTERBAND
        return {"route": route, "engine_id": engine_id, "full_bz_required": True,
                "derived_properties": specification.requested_derived_properties,
                "warnings": self.warnings(specification, system, route)}

    @staticmethod
    def warnings(specification, system, route):
        warnings = ["EXCITONIC_EFFECTS_NOT_INCLUDED", "SEMILOCAL_BAND_GAP_LIMITATION"]
        if route is OpticalRoute.SLAB_SUPERCELL_RAW:
            warnings.append("2D_SUPERCELL_NORMALIZATION")
        if route is OpticalRoute.BULK_METALLIC:
            warnings.append("METALLIC_INTRABAND_RESPONSE")
        if specification.hybrid_functional or system.hybrid_functional:
            warnings.append("HYBRID_OPTICS_UNVERIFIED")
        return tuple(warnings)
