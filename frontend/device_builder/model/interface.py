"""Qt-free semantic model for a commensurate DeviceRegion interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Any
from uuid import uuid4


class InterfaceMode(str, Enum):
    ALIGNED = "aligned"
    TWISTED = "twisted"


VALID_INTERFACE_STRAIN_MODES = ("balanced", "bottom", "top")


@dataclass
class DeviceInterface:
    region_a_id: str
    region_b_id: str
    mode: InterfaceMode = InterfaceMode.ALIGNED
    requested_twist_deg: float = 0.0
    max_strain: float = 0.05
    strain_mode: str = "balanced"
    gap: float = 3.0
    max_index: int = 3
    diagnostics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        self.mode = InterfaceMode(self.mode)
        self.requested_twist_deg = float(self.requested_twist_deg)
        self.max_strain = float(self.max_strain)
        self.gap = float(self.gap)
        self.max_index = int(self.max_index)
        self.strain_mode = str(self.strain_mode).strip().lower()
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Device interface requires a non-empty id.")
        if not isinstance(self.region_a_id, str) or not self.region_a_id.strip():
            raise ValueError("Device interface requires region A id.")
        if not isinstance(self.region_b_id, str) or not self.region_b_id.strip():
            raise ValueError("Device interface requires region B id.")
        if self.region_a_id == self.region_b_id:
            raise ValueError("Device interface regions must be different.")
        if not isfinite(self.requested_twist_deg):
            raise ValueError("Requested twist must be finite.")
        if self.mode is InterfaceMode.ALIGNED and abs(self.requested_twist_deg) > 1e-12:
            raise ValueError("Aligned interfaces require zero requested twist.")
        if not isfinite(self.max_strain) or self.max_strain < 0.0:
            raise ValueError("Interface max strain must be finite and non-negative.")
        if self.strain_mode not in VALID_INTERFACE_STRAIN_MODES:
            raise ValueError("Interface strain mode must be balanced, bottom, or top.")
        if not isfinite(self.gap) or self.gap < 0.0:
            raise ValueError("Interface gap must be finite and non-negative.")
        if self.max_index < 1:
            raise ValueError("Interface max_index must be at least 1.")
        if not isinstance(self.diagnostics, dict) or not isinstance(self.metadata, dict):
            raise ValueError("Interface diagnostics and metadata must be dictionaries.")

    def to_dict(self):
        return {
            "id": self.id,
            "region_a_id": self.region_a_id,
            "region_b_id": self.region_b_id,
            "mode": self.mode.value,
            "requested_twist_deg": self.requested_twist_deg,
            "max_strain": self.max_strain,
            "strain_mode": self.strain_mode,
            "gap": self.gap,
            "max_index": self.max_index,
            "diagnostics": dict(self.diagnostics),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Device interface data must be a dictionary.")
        return cls(
            id=data.get("id"),
            region_a_id=data.get("region_a_id"),
            region_b_id=data.get("region_b_id"),
            mode=data.get("mode", InterfaceMode.ALIGNED.value),
            requested_twist_deg=data.get("requested_twist_deg", 0.0),
            max_strain=data.get("max_strain", 0.05),
            strain_mode=data.get("strain_mode", "balanced"),
            gap=data.get("gap", 3.0),
            max_index=data.get("max_index", 3),
            diagnostics=dict(data.get("diagnostics", {})),
            metadata=dict(data.get("metadata", {})),
        )
