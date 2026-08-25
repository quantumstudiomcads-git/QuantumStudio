"""One generic generated-workflow input consumed by LocalExecutionManager."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from backend.core.execution_contract import ArtifactLocality, CommandSpec
@dataclass(frozen=True)
class GeneratedTask:
 task_id:str; semantic_task_type:str; engine_id:str; tool_id:str; working_directory:str; command:CommandSpec; dependencies:tuple[str,...]=(); input_files:tuple[str,...]=(); artifact_inputs:tuple[str,...]=(); artifact_outputs:tuple[str,...]=(); artifact_locality:dict[str,ArtifactLocality]=field(default_factory=dict); timeout_seconds:float|None=None
@dataclass(frozen=True)
class GeneratedWorkflow:
 request_id:str; root:Path; tasks:tuple[GeneratedTask,...]; manifest_filename:str="manifest.json"; external_artifacts:dict[str,Path]=field(default_factory=dict)
 def task_map(self): return {task.task_id:task for task in self.tasks}
