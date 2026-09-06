"""Boundary conversion from adapter task inputs to C6's generic contract.

This module deliberately understands only the stable generated-task shape used by
the adapters.  The scheduler never receives QE, Wannier, EPW, or BTP2 objects.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from backend.core.execution_contract import CommandSpec, ExecutionMode
from backend.engines.registry import engine_descriptor

from .generated import GeneratedTask, GeneratedWorkflow


def _command_for(task, metadata: dict[str, object], mode: ExecutionMode) -> CommandSpec:
    command = metadata.get("command")
    if isinstance(command, (list, tuple)) and command and all(isinstance(part, str) for part in command):
        program, arguments, stdin = command[0], tuple(command[1:]), None
    else:
        program, arguments, stdin = task.executable, (), task.input_filename
    return CommandSpec(
        program=program,
        arguments=arguments,
        stdin_file=stdin,
        stdout_file=task.output_filename,
        stderr_file=f"{task.output_filename}.err",
        working_directory=task.working_directory,
        execution_mode=mode,
    )


def normalize_adapter_tasks(
    request_id: str,
    workflow_root: str | Path,
    task_inputs: Iterable[object],
    *,
    external_artifacts: dict[str, str] | None = None,
) -> GeneratedWorkflow:
    """Convert generated adapter task records to one executor-facing workflow.

    Adapter records carry a common, intentionally small field set.  Command details
    may be supplied declaratively in ``metadata['command']``; no program name is
    inferred from a calculation or engine name here.
    """
    tasks: list[GeneratedTask] = []
    for input_task in task_inputs:
        metadata = dict(getattr(input_task, "metadata", {}) or {})
        engine_id = str(metadata.get("engine_id", "quantum_espresso"))
        descriptor = engine_descriptor(engine_id)
        mode = descriptor.execution_mode
        command = _command_for(input_task, metadata, mode)
        tasks.append(GeneratedTask(
            task_id=input_task.task_id,
            semantic_task_type=str(metadata.get("semantic_task_type", input_task.calculation_id)),
            engine_id=engine_id,
            tool_id=input_task.executable,
            working_directory=input_task.working_directory,
            command=command,
            dependencies=tuple(input_task.depends_on_task_ids),
            input_files=(input_task.input_filename,),
            artifact_inputs=tuple(metadata.get("artifact_inputs", ())),
            artifact_outputs=tuple(metadata.get("artifact_outputs", ())),
            artifact_declarations=tuple(metadata.get("artifact_declarations", ())),
            artifact_requirements=tuple(metadata.get("artifact_requirements", ())),
            metadata=metadata,
        ))
    return GeneratedWorkflow(
        request_id=request_id,
        root=Path(workflow_root),
        tasks=tuple(tasks),
        external_artifacts=dict(external_artifacts or {}),
    )
