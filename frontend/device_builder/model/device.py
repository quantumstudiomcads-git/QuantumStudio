from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4
from .region import DeviceRegion

VALID_TRANSPORT_DIRECTIONS = ("X", "Y", "Z")


@dataclass
class Device:
    name: str = "Untitled Device"
    regions: list[DeviceRegion] = field(default_factory=list)
    cell: list[list[float]] | None = None
    periodic: tuple[bool, bool, bool] = (False, False, False)
    transport_direction: str = "Z"
    padding: tuple[float, float, float] = (5.0, 5.0, 5.0)
    origin_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    _last_assembly: object = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.periodic = tuple(self.periodic)
        self.padding = tuple(float(value) for value in self.padding)
        self.origin_offset = tuple(float(value) for value in self.origin_offset)
        if not isinstance(self.metadata, dict):
            raise ValueError("Device metadata must be a dictionary.")
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Device requires a non-empty id.")

    def add_region(self, region):
        if not isinstance(region, DeviceRegion):
            raise TypeError("Device accepts DeviceRegion instances.")
        if any(existing.id == region.id for existing in self.regions):
            raise ValueError(f"Duplicate region id: {region.id}")
        self.regions.append(region)
        return region

    def get_region(self, region_id):
        return next((region for region in self.regions if region.id == region_id), None)

    def remove_region(self, region_id):
        region = self.get_region(region_id)
        if region is None:
            return False
        self.regions.remove(region)
        return True

    def duplicate_region(self, region_id):
        region = self.get_region(region_id)
        if region is None:
            raise KeyError(f"Unknown region id: {region_id}")
        duplicate = region.duplicate()
        return self.add_region(duplicate)

    def assemble_with_membership(self):
        from frontend.device_builder.assembly.assembler import assemble_device
        self._last_assembly = assemble_device(self)
        return self._last_assembly

    def assemble(self):
        return self.assemble_with_membership().structure

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "regions": [region.to_dict() for region in self.regions],
            "cell": None if self.cell is None else [[float(value) for value in vector] for vector in self.cell],
            "periodic": list(self.periodic),
            "transport_direction": self.transport_direction,
            "padding": list(self.padding),
            "origin_offset": list(self.origin_offset),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Device data must be a dictionary.")
        regions_data = data.get("regions", [])
        if not isinstance(regions_data, list):
            raise ValueError("Device regions must be a list.")
        return cls(
            id=data.get("id"),
            name=data.get("name", "Untitled Device"),
            regions=[DeviceRegion.from_dict(item) for item in regions_data],
            cell=data.get("cell"),
            periodic=data.get("periodic", (False, False, False)),
            transport_direction=data.get("transport_direction", "Z"),
            padding=data.get("padding", (5.0, 5.0, 5.0)),
            origin_offset=data.get("origin_offset", (0.0, 0.0, 0.0)),
            metadata=dict(data.get("metadata", {})),
        )
