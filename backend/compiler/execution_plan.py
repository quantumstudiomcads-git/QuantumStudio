"""Engine-agnostic, derived execution plan for one calculation request."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class PlannedTask:
    """A semantic executable calculation stage, with explicit DAG edges."""

    id: str
    calculation_id: str
    semantic_task_type: str | None = None
    engine_id: str | None = None
    tool_id: str | None = None
    parameter_signature: str = ""
    artifact_inputs: tuple[str, ...] = ()
    artifact_outputs: tuple[str, ...] = ()
    depends_on_task_ids: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    structure_reference: str = "request_snapshot"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "calculation_id": self.calculation_id,
            "semantic_task_type": self.semantic_task_type or self.calculation_id,
            "engine_id": self.engine_id,
            "tool_id": self.tool_id,
            "parameter_signature": self.parameter_signature,
            "artifact_inputs": list(self.artifact_inputs),
            "artifact_outputs": list(self.artifact_outputs),
            "depends_on_task_ids": list(self.depends_on_task_ids),
            "parameters": dict(self.parameters),
            "structure_reference": self.structure_reference,
            "metadata": dict(self.metadata),
        }


@dataclass
class ExecutionPlan:
    calculation_id: str
    selected_calculations: list[str]
    resolved_calculations: list[str]
    execution_target: str
    parameters: dict[str, Any] = field(default_factory=dict)
    calculation_parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    structure: dict[str, Any] = field(default_factory=dict)
    tasks: list[PlannedTask] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def task_for_calculation(self, calculation_id: str) -> PlannedTask:
        for task in self.tasks:
            if task.calculation_id == calculation_id:
                return task
        raise KeyError(f"No planned task for calculation: {calculation_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_plan": {
                "id": self.id,
                "calculation_id": self.calculation_id,
                "created_at": self.created_at,
                "target": self.execution_target,
                "selected": list(self.selected_calculations),
                "resolved": list(self.resolved_calculations),
                "parameters": dict(self.parameters),
                "calculation_parameters": dict(self.calculation_parameters),
                "structure": dict(self.structure),
                "tasks": [task.to_dict() for task in self.tasks],
                "metadata": dict(self.metadata),
            }
        }
