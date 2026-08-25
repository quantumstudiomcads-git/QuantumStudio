"""C5E shared non-executing contract types consumed by the future C6 executor."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

class GenerationSupport(str, Enum): CAN_GENERATE="CAN_GENERATE"; DEFERRED="DEFERRED"; NOT_APPLICABLE="NOT_APPLICABLE"
class ExecutionReadiness(str, Enum): GENERATION_READY="GENERATION_READY"; EXECUTION_BACKEND_MISSING="EXECUTION_BACKEND_MISSING"; INPUTS_INCOMPLETE="INPUTS_INCOMPLETE"; EXTERNAL_ARTIFACT_REQUIRED="EXTERNAL_ARTIFACT_REQUIRED"; UNSUPPORTED="UNSUPPORTED"
class ExecutionMode(str, Enum): SUBPROCESS="SUBPROCESS"; PYTHON_API="PYTHON_API"; INTERNAL_BACKEND="INTERNAL_BACKEND"; NOT_SELECTED="NOT_SELECTED"
class ArtifactLocality(str, Enum): SHARED_WORKFLOW="SHARED_WORKFLOW"; TASK_LOCAL="TASK_LOCAL"; EXTERNAL="EXTERNAL"

@dataclass(frozen=True)
class CommandSpec:
    """Structured future invocation; it deliberately has no execute method."""
    program: str
    arguments: tuple[str, ...] = ()
    stdin_file: str | None = None
    stdout_file: str | None = None
    stderr_file: str | None = None
    working_directory: str | None = None
    environment: dict[str, str] = field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.SUBPROCESS
    def __post_init__(self):
        if not self.program or any(any(token in value for token in "|;&><") for value in (self.program,*self.arguments)):
            raise ValueError("CommandSpec requires program/arguments without shell metacharacters.")
    def to_dict(self):
        return {"program":self.program,"arguments":list(self.arguments),"stdin_file":self.stdin_file,"stdout_file":self.stdout_file,"stderr_file":self.stderr_file,"working_directory":self.working_directory,"environment":dict(self.environment),"execution_mode":self.execution_mode.value}
