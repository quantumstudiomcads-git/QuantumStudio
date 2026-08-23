"""Qt-free Device Template contract and common construction helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Iterable

from frontend.core import Structure
from frontend.device_builder.assembly import detect_inter_region_collisions, fit_device_cell


@dataclass(frozen=True)
class TemplateBuildResult:
    """A complete, uncommitted Device template build result."""

    device: Any
    warnings: tuple[str, ...] = ()
    interface_diagnostics: dict[str, Any] | None = None
    atom_count: int = 0
    collisions: tuple[Any, ...] = ()


class DeviceTemplate(ABC):
    """Qt-free transactional convenience constructor for a Device."""

    id: str
    name: str
    description: str
    required_inputs: tuple[str, ...] = ()

    @abstractmethod
    def validate(self, **parameters) -> None:
        """Raise ``ValueError`` before any Device is created for invalid input."""

    @abstractmethod
    def build(self, **parameters) -> TemplateBuildResult:
        """Return a new Device without mutating an active Device or any input Structure."""


def require_structure(value: Any, label: str) -> Structure:
    if not isinstance(value, Structure):
        raise ValueError(f"{label} must be a native Quantum Studio Structure.")
    if not value.atoms:
        raise ValueError(f"{label} must contain at least one atom.")
    return value


def nonnegative_finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a finite non-negative value.") from error
    if not isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be a finite non-negative value.")
    return number


def finite_vector(value: Iterable[float], label: str, *, nonnegative: bool = False) -> tuple[float, float, float]:
    values = tuple(float(item) for item in value)
    if len(values) != 3 or not all(isfinite(item) for item in values):
        raise ValueError(f"{label} must contain three finite values.")
    if nonnegative and any(item < 0.0 for item in values):
        raise ValueError(f"{label} values must be non-negative.")
    return values


def provenance(template: DeviceTemplate, parameters: dict[str, Any]) -> dict[str, Any]:
    """Produce serializable non-authoritative template provenance."""
    return {
        "template_id": template.id,
        "template_name": template.name,
        "template_parameters": dict(parameters),
    }


def finalize_template_device(device, template: DeviceTemplate, *, parameters: dict[str, Any], padding) -> TemplateBuildResult:
    """Fit the derived Device cell and report non-blocking collision diagnostics."""
    padding = finite_vector(padding, "Padding", nonnegative=True)
    fit_device_cell(device, padding)
    device.metadata.update(provenance(template, parameters))
    collisions = detect_inter_region_collisions(device)
    warnings = () if not collisions else (f"{len(collisions)} possible inter-region atomic overlap(s) detected.",)
    return TemplateBuildResult(
        device=device,
        warnings=warnings,
        atom_count=sum(len(region.source_structure.atoms) for region in device.regions if region.visible),
        collisions=collisions,
    )
