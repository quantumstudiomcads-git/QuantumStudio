"""
Quantum Studio Execution Plan

The fully resolved representation of a calculation request.

Each calculation receives its own parameter set.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class ExecutionPlan:

    calculation_id: str

    selected_calculations: list[str]

    resolved_calculations: list[str]

    execution_target: str

    parameters: dict[str, Any] = field(
        default_factory=dict
    )

    calculation_parameters: dict[
        str,
        dict[str, Any],
    ] = field(
        default_factory=dict
    )

    structure: dict[str, Any] = field(
        default_factory=dict
    )

    created_at: str = field(
        default_factory=lambda:
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    id: str = field(
        default_factory=lambda:
        str(uuid4())
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:

        return {

            "execution_plan": {

                "id":
                    self.id,

                "calculation_id":
                    self.calculation_id,

                "created_at":
                    self.created_at,

                "target":
                    self.execution_target,

                "selected":
                    self.selected_calculations,

                "resolved":
                    self.resolved_calculations,

                "parameters":
                    self.parameters,

                "calculation_parameters":
                    self.calculation_parameters,

                "structure":
                    self.structure,

                "metadata":
                    self.metadata,
            }
        }
