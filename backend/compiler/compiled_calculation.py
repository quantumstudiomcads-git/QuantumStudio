"""
Quantum Studio Compiled Calculation

Represents a calculation after dependency resolution.

This object is created by the calculation compiler and contains
the information required by the execution system.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompiledCalculation:

    id: str

    name: str

    workflow: str | None

    engine: str | None

    requires: tuple[str, ...] = field(
        default_factory=tuple
    )

    produces: tuple[str, ...] = field(
        default_factory=tuple
    )

    parameters: dict[str, Any] = field(
        default_factory=dict
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict:

        return {
            "id": self.id,
            "name": self.name,
            "workflow": self.workflow,
            "engine": self.engine,
            "requires": list(self.requires),
            "produces": list(self.produces),
            "parameters": self.parameters,
            "metadata": self.metadata,
        }
