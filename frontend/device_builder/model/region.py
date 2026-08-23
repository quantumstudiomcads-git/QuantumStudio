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
