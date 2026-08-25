"""Qt-free, execution-free domain contracts for multi-component NEGF transport."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from collections.abc import Mapping, Sequence
from typing import Any


WANNIER_HAMILTONIAN = "wannier_hr"  # Existing C5A semantic artifact contract.
TRANSPORT_HAMILTONIAN = "TRANSPORT_HAMILTONIAN"
TRANSPORT_OVERLAP = "TRANSPORT_OVERLAP"


class TransportModelError(ValueError):
    pass


class ComponentRole(str, Enum):
    LEFT_ELECTRODE = "LEFT_ELECTRODE"
    CENTRAL_REGION = "CENTRAL_REGION"
    RIGHT_ELECTRODE = "RIGHT_ELECTRODE"


class HamiltonianSourceMode(str, Enum):
    WANNIER90 = "WANNIER90"
    EXTERNAL_TIGHT_BINDING = "EXTERNAL_TIGHT_BINDING"


class SpinMode(str, Enum):
    SPIN_DEGENERATE = "SPIN_DEGENERATE"
    SPIN_RESOLVED = "SPIN_RESOLVED"
    SPINOR = "SPINOR"


def _triple(value: object, label: str, *, integers: bool = False, positive: bool = False) -> tuple[float, float, float] | tuple[int, int, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise TransportModelError(f"{label} must contain exactly three values.")
    try:
        converted = tuple(int(item) if integers else float(item) for item in value)
    except (TypeError, ValueError) as error:
        raise TransportModelError(f"{label} must contain numeric values.") from error
    if not all(isfinite(float(item)) for item in converted) or (positive and any(item < 1 for item in converted)):
        raise TransportModelError(f"{label} values are invalid.")
    if integers and any(item != original for item, original in zip(converted, value)):
        raise TransportModelError(f"{label} must contain positive integers.")
    return converted


@dataclass(frozen=True)
class ArtifactReference:
    """A semantic future artifact reference, never an in-memory numerical matrix."""
    artifact_type: str
    reference_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.artifact_type or not self.reference_id:
            raise TransportModelError("Artifact references require type and stable reference_id.")

    def to_dict(self):
        return {"artifact_type": self.artifact_type, "reference_id": self.reference_id, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class HamiltonianSource:
    mode: HamiltonianSourceMode
    hamiltonian: ArtifactReference
    overlap: ArtifactReference | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.mode is HamiltonianSourceMode.WANNIER90 and self.hamiltonian.artifact_type != WANNIER_HAMILTONIAN:
            raise TransportModelError("WANNIER90 Hamiltonian sources must consume the existing wannier_hr artifact contract.")
        if self.overlap is not None and self.overlap.artifact_type != TRANSPORT_OVERLAP:
            raise TransportModelError("Explicit overlap must use the TRANSPORT_OVERLAP artifact contract.")

    @property
    def basis_kind(self) -> str:
        return "NONORTHOGONAL" if self.overlap else "ORTHOGONAL_S_EQUALS_IDENTITY"

    def to_dict(self):
        return {"mode": self.mode.value, "hamiltonian": self.hamiltonian.to_dict(), "overlap": self.overlap.to_dict() if self.overlap else None, "basis_kind": self.basis_kind, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class TransportComponent:
    id: str
    role: ComponentRole
    structure_snapshot: dict[str, Any]
    hamiltonian_source: HamiltonianSource
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id or not isinstance(self.structure_snapshot, Mapping):
            raise TransportModelError("Transport components require an ID and serialized structure snapshot contract.")

    def to_dict(self):
        return {"id": self.id, "role": self.role.value, "structure_snapshot": dict(self.structure_snapshot), "hamiltonian_source": self.hamiltonian_source.to_dict(), "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class PrincipalLayer:
    transport_vector: tuple[float, float, float]
    repeat_count: int
    onsite_hamiltonian: ArtifactReference
    coupling_hamiltonian: ArtifactReference
    onsite_overlap: ArtifactReference | None = None
    coupling_overlap: ArtifactReference | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        _triple(self.transport_vector, "principal-layer transport_vector")
        if int(self.repeat_count) < 1:
            raise TransportModelError("Principal-layer repeat_count must be positive.")
        if self.onsite_hamiltonian.artifact_type != TRANSPORT_HAMILTONIAN or self.coupling_hamiltonian.artifact_type != TRANSPORT_HAMILTONIAN:
            raise TransportModelError("Principal-layer onsite and coupling references must be TRANSPORT_HAMILTONIAN artifacts.")
        if (self.onsite_overlap is None) != (self.coupling_overlap is None):
            raise TransportModelError("Principal-layer overlap references must be supplied together.")

    def to_dict(self):
        return {"transport_vector": list(self.transport_vector), "repeat_count": self.repeat_count, "onsite_hamiltonian": self.onsite_hamiltonian.to_dict(), "coupling_hamiltonian": self.coupling_hamiltonian.to_dict(), "onsite_overlap": self.onsite_overlap.to_dict() if self.onsite_overlap else None, "coupling_overlap": self.coupling_overlap.to_dict() if self.coupling_overlap else None, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class ElectrodeModel:
    component: TransportComponent
    principal_layer: PrincipalLayer
    chemical_potential_ev: float
    temperature_kelvin: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.component.role not in {ComponentRole.LEFT_ELECTRODE, ComponentRole.RIGHT_ELECTRODE}:
            raise TransportModelError("ElectrodeModel requires a left or right electrode component.")
        if not isfinite(float(self.chemical_potential_ev)) or not isfinite(float(self.temperature_kelvin)) or self.temperature_kelvin < 0:
            raise TransportModelError("Electrode chemical potential must be finite and temperature must be non-negative.")

    def to_dict(self):
        return {"component": self.component.to_dict(), "principal_layer": self.principal_layer.to_dict(), "chemical_potential_ev": self.chemical_potential_ev, "temperature_kelvin": self.temperature_kelvin, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class CentralRegionModel:
    component: TransportComponent
    left_coupling: ArtifactReference
    right_coupling: ArtifactReference
    overlap: ArtifactReference | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.component.role is not ComponentRole.CENTRAL_REGION:
            raise TransportModelError("CentralRegionModel requires a CENTRAL_REGION component.")
        if self.left_coupling.artifact_type != TRANSPORT_HAMILTONIAN or self.right_coupling.artifact_type != TRANSPORT_HAMILTONIAN:
            raise TransportModelError("Central-region couplings must be TRANSPORT_HAMILTONIAN artifacts.")
        if self.overlap is not None and self.overlap.artifact_type != TRANSPORT_OVERLAP:
            raise TransportModelError("Central-region overlap must use TRANSPORT_OVERLAP.")

    def to_dict(self):
        return {"component": self.component.to_dict(), "left_coupling": self.left_coupling.to_dict(), "right_coupling": self.right_coupling.to_dict(), "overlap": self.overlap.to_dict() if self.overlap else None, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class TransportInput:
    id: str
    transport_direction: str
    left_electrode: ElectrodeModel
    central_region: CentralRegionModel
    right_electrode: ElectrodeModel
    transverse_periodicity: tuple[bool, bool, bool]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        direction = str(self.transport_direction).upper()
        if not self.id or direction not in {"X", "Y", "Z"}:
            raise TransportModelError("TransportInput requires a stable ID and transport direction X, Y, or Z.")
        if len(self.transverse_periodicity) != 3 or not all(isinstance(value, bool) for value in self.transverse_periodicity):
            raise TransportModelError("transverse_periodicity must be three Boolean values.")
        axis = "XYZ".index(direction)
        if self.transverse_periodicity[axis]:
            raise TransportModelError("transverse_periodicity must be false along the transport direction.")
        if self.left_electrode.component.role is not ComponentRole.LEFT_ELECTRODE or self.right_electrode.component.role is not ComponentRole.RIGHT_ELECTRODE:
            raise TransportModelError("TransportInput requires explicitly sided electrode models.")

    def to_dict(self):
        return {"schema_version": 1, "id": self.id, "transport_direction": self.transport_direction.upper(), "left_electrode": self.left_electrode.to_dict(), "central_region": self.central_region.to_dict(), "right_electrode": self.right_electrode.to_dict(), "transverse_periodicity": list(self.transverse_periodicity), "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class NEGFSettings:
    energy_min_ev: float | None = None
    energy_max_ev: float | None = None
    energy_points: int | None = None
    energies_ev: tuple[float, ...] = ()
    eta_ev: float = 1.0e-5
    mu_left_ev: float = 0.0
    mu_right_ev: float = 0.0
    temperature_left_kelvin: float = 300.0
    temperature_right_kelvin: float = 300.0
    transverse_k_mesh: tuple[int, int, int] = (1, 1, 1)
    spin_mode: SpinMode = SpinMode.SPIN_DEGENERATE
    effective_degeneracy: int | None = None
    hamiltonian_source_mode: HamiltonianSourceMode = HamiltonianSourceMode.WANNIER90
    bias_convention: str = "V_bias = (mu_left - mu_right) / e"

    def __post_init__(self):
        explicit = bool(self.energies_ev)
        ranged = self.energy_min_ev is not None or self.energy_max_ev is not None or self.energy_points is not None
        if explicit == ranged:
            raise TransportModelError("Specify exactly one explicit energy list or energy_min_ev/energy_max_ev/energy_points.")
        if explicit:
            values = tuple(float(value) for value in self.energies_ev)
            if len(values) < 2 or not all(isfinite(value) for value in values) or any(a >= b for a, b in zip(values, values[1:])):
                raise TransportModelError("energies_ev must contain at least two finite ascending eV values.")
        else:
            if not all(value is not None for value in (self.energy_min_ev, self.energy_max_ev, self.energy_points)) or not self.energy_min_ev < self.energy_max_ev or int(self.energy_points) < 2:
                raise TransportModelError("Require energy_min_ev < energy_max_ev and energy_points >= 2.")
        if not isfinite(float(self.eta_ev)) or self.eta_ev <= 0:
            raise TransportModelError("eta_ev must be finite and > 0.")
        if any(not isfinite(float(value)) or value < 0 for value in (self.temperature_left_kelvin, self.temperature_right_kelvin)):
            raise TransportModelError("Electrode temperatures must be finite and non-negative K.")
        _triple(self.transverse_k_mesh, "transverse_k_mesh", integers=True, positive=True)
        if not self.bias_convention or "mu_left" not in self.bias_convention or "mu_right" not in self.bias_convention:
            raise TransportModelError("bias_convention must explicitly state mu_left and mu_right.")
        default = 2 if self.spin_mode is SpinMode.SPIN_DEGENERATE else 1
        deg = default if self.effective_degeneracy is None else int(self.effective_degeneracy)
        if deg < 1:
            raise TransportModelError("effective_degeneracy must be positive.")
        object.__setattr__(self, "effective_degeneracy", deg)

    def validate_for(self, transport: TransportInput):
        axis = "XYZ".index(transport.transport_direction.upper())
        mesh = _triple(self.transverse_k_mesh, "transverse_k_mesh", integers=True, positive=True)
        if mesh[axis] != 1:
            raise TransportModelError("transverse_k_mesh must be 1 along the transport direction.")
        for index, periodic in enumerate(transport.transverse_periodicity):
            if not periodic and mesh[index] != 1:
                raise TransportModelError("transverse_k_mesh must be 1 for non-periodic directions.")
        modes = {transport.left_electrode.component.hamiltonian_source.mode, transport.central_region.component.hamiltonian_source.mode, transport.right_electrode.component.hamiltonian_source.mode}
        if modes != {self.hamiltonian_source_mode}:
            raise TransportModelError("NEGF settings hamiltonian_source_mode must match all three component sources.")

    def to_dict(self):
        return {"energy_grid": {"energies_ev": list(self.energies_ev), "energy_min_ev": self.energy_min_ev, "energy_max_ev": self.energy_max_ev, "energy_points": self.energy_points}, "eta_ev": self.eta_ev, "chemical_potentials_ev": {"left": self.mu_left_ev, "right": self.mu_right_ev}, "temperatures_kelvin": {"left": self.temperature_left_kelvin, "right": self.temperature_right_kelvin}, "transverse_k_mesh": list(self.transverse_k_mesh), "spin_mode": self.spin_mode.value, "effective_degeneracy": self.effective_degeneracy, "hamiltonian_source_mode": self.hamiltonian_source_mode.value, "bias_convention": self.bias_convention}
