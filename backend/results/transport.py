"""Validated BoltzTraP2 transport result contract."""
from __future__ import annotations

from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path
import numpy as np

from .models import ResultProvenance, ResultStatus, ScientificResult


class TransportParseError(ValueError):
    pass


@dataclass(frozen=True)
class TransportResult:
    temperatures_K: np.ndarray
    chemical_potential_eV: np.ndarray
    carrier_concentration_cm3: np.ndarray
    electrical_conductivity_over_tau: np.ndarray
    seebeck: np.ndarray
    electronic_thermal_conductivity_over_tau: np.ndarray
    power_factor_over_tau: np.ndarray | None
    metadata: dict

    @classmethod
    def from_json(cls, path: str | Path) -> "TransportResult":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TransportParseError("BoltzTraP2 transport artifact is missing or invalid.") from error
        if not isinstance(payload, dict) or not payload.get("units") or not payload.get("method_assumptions"):
            raise TransportParseError("Transport artifact must declare units and method assumptions.")
        def array(name, ndim=None):
            value = np.asarray(payload.get(name), dtype=float)
            if value.size == 0 or not np.all(np.isfinite(value)) or (ndim is not None and value.ndim != ndim):
                raise TransportParseError(f"Transport field {name} is empty, nonfinite, or has the wrong shape.")
            return value
        temperature = array("temperatures_K", 1)
        chemical = array("chemical_potential_eV", 1)
        if np.any(temperature <= 0): raise TransportParseError("temperatures_K must be positive.")
        conductivity = array("electrical_conductivity_over_tau", 4)
        seebeck = array("seebeck", 4)
        thermal = array("electronic_thermal_conductivity_over_tau", 4)
        if conductivity.shape[-2:] != (3, 3) or seebeck.shape[-2:] != (3, 3) or thermal.shape[-2:] != (3, 3):
            raise TransportParseError("Transport tensors must have trailing shape (3, 3).")
        expected = (len(temperature), len(chemical), 3, 3)
        for name, value in (("electrical_conductivity_over_tau", conductivity), ("seebeck", seebeck), ("electronic_thermal_conductivity_over_tau", thermal)):
            if value.shape != expected: raise TransportParseError(f"{name} shape must be {expected}.")
        carrier = array("carrier_concentration_cm3", 2)
        if carrier.shape != (len(temperature), len(chemical)): raise TransportParseError("carrier_concentration_cm3 shape mismatch.")
        power = payload.get("power_factor_over_tau")
        power_array = None if power is None else array("power_factor_over_tau", 4)
        if power_array is not None and power_array.shape != expected: raise TransportParseError("power_factor_over_tau shape mismatch.")
        return cls(temperature, chemical, carrier, conductivity, seebeck, thermal, power_array, dict(payload))


def parse_transport_result(path, *, request_id="", execution_id="", task_id="", **_parser_context):
    parsed = TransportResult.from_json(path)
    provenance = ResultProvenance(request_id, execution_id, task_id, "boltztrap2", "btp2", (str(Path(path)),), {str(Path(path)): __import__("hashlib").sha256(Path(path).read_bytes()).hexdigest()}, "btp2.transport.json")
    arrays = {
        "temperatures_K": parsed.temperatures_K, "chemical_potential_eV": parsed.chemical_potential_eV,
        "carrier_concentration_cm3": parsed.carrier_concentration_cm3,
        "electrical_conductivity_over_tau": parsed.electrical_conductivity_over_tau,
        "seebeck": parsed.seebeck, "electronic_thermal_conductivity_over_tau": parsed.electronic_thermal_conductivity_over_tau,
    }
    if parsed.power_factor_over_tau is not None: arrays["power_factor_over_tau"] = parsed.power_factor_over_tau
    return ScientificResult("TransportResult", ResultStatus.VALID, provenance, arrays=arrays, metadata=parsed.metadata)
