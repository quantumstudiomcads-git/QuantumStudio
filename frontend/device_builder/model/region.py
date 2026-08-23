from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4
from frontend.core.structure import Structure
from .roles import RegionRole


@dataclass
class DeviceRegion:
    source_structure: Structure
    name: str = "Region"
    role: RegionRole = RegionRole.OTHER
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    visible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        self.role = RegionRole(self.role)
        self.translation = tuple(float(value) for value in self.translation)
        self.rotation = tuple(float(value) for value in self.rotation)
        if len(self.translation) != 3 or len(self.rotation) != 3:
            raise ValueError("Region translation and rotation must each have three values.")
        if not isinstance(self.metadata, dict):
            raise ValueError("Region metadata must be a dictionary.")
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Region requires a non-empty id.")

    def transformed_structure(self):
        from frontend.device_builder.assembly.transforms import transform_structure
        return transform_structure(self.source_structure, self.translation, self.rotation)

    def duplicate(self, name=None):
        return DeviceRegion(
            source_structure=self.source_structure.copy(),
            name=name or f"{self.name} Copy", role=self.role,
            translation=tuple(self.translation), rotation=tuple(self.rotation),
            visible=self.visible, metadata=dict(self.metadata),
        )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role.value,
            "source_structure": self.source_structure.to_dict(),
            "translation": list(self.translation),
            "rotation": list(self.rotation),
            "visible": bool(self.visible),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Device region data must be a dictionary.")
        source_data = data.get("source_structure")
        if not isinstance(source_data, dict):
            raise ValueError("Device region requires a serialized source Structure.")
        return cls(
            id=data.get("id"),
            name=data.get("name", "Region"),
            role=data.get("role", RegionRole.OTHER.value),
            source_structure=Structure.from_dict(source_data),
            translation=data.get("translation", (0.0, 0.0, 0.0)),
            rotation=data.get("rotation", (0.0, 0.0, 0.0)),
            visible=bool(data.get("visible", True)),
            metadata=dict(data.get("metadata", {})),
        )
