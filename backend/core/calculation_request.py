"""Serializable scientific intent shared by Calculate and the backend compiler."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


CALCULATION_REQUEST_SCHEMA_VERSION = "0.1"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CalculationRequest:
    """Persistent request input; execution plans remain derived and non-persistent."""

    structure: dict[str, Any]
    selected_calculations: list[str]
    parameters: dict[str, Any] = field(default_factory=dict)
    execution_target: str = "local"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=_timestamp)
    metadata: dict[str, Any] = field(default_factory=dict)
    name: str = ""
    updated_at: str | None = None
    schema_version: str = CALCULATION_REQUEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Calculation request requires a non-empty id.")
        if not isinstance(self.structure, dict):
            raise ValueError("Calculation request structure must be a serialized native Structure dictionary.")
        if not isinstance(self.selected_calculations, list) or not self.selected_calculations:
            raise ValueError("Calculation request requires at least one selected calculation.")
        if not all(isinstance(item, str) and item.strip() for item in self.selected_calculations):
            raise ValueError("Calculation request identifiers must be non-empty strings.")
        if not isinstance(self.parameters, dict) or not isinstance(self.metadata, dict):
            raise ValueError("Calculation request parameters and metadata must be dictionaries.")
        self.selected_calculations = list(self.selected_calculations)
        self.parameters = deepcopy(self.parameters)
        self.metadata = deepcopy(self.metadata)
        self.structure = deepcopy(self.structure)
        self.name = str(self.name).strip()

    @property
    def calculation_id(self) -> str:
        """Primary user-requested workflow identifier for list/display purposes."""
        return self.selected_calculations[0]

    def to_persistence_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "structure": deepcopy(self.structure),
            "selected_calculations": list(self.selected_calculations),
            "parameters": deepcopy(self.parameters),
            "execution_target": self.execution_target,
            "metadata": deepcopy(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        """Preserve the established wrapper shape for existing backend callers."""
        return {"calculation_request": self.to_persistence_dict()}

    @classmethod
    def from_persistence_dict(cls, data: dict[str, Any]) -> "CalculationRequest":
        if not isinstance(data, dict):
            raise ValueError("Calculation request data must be a dictionary.")
        if "calculation_request" in data:
            data = data["calculation_request"]
        return cls(
            id=data.get("id"), name=data.get("name", ""), created_at=data.get("created_at", _timestamp()),
            updated_at=data.get("updated_at"), schema_version=data.get("schema_version", CALCULATION_REQUEST_SCHEMA_VERSION),
            structure=data.get("structure"), selected_calculations=data.get("selected_calculations"),
            parameters=data.get("parameters", {}), execution_target=data.get("execution_target", "local"),
            metadata=data.get("metadata", {}),
        )

    def copy_with(self, *, new_id: bool = False, **changes) -> "CalculationRequest":
        values = self.to_persistence_dict()
        values.update(changes)
        if new_id:
            values["id"] = str(uuid4())
            values["created_at"] = _timestamp()
            values["updated_at"] = None
        return CalculationRequest.from_persistence_dict(values)
