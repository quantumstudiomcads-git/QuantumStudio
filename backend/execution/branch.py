"""Realization of a compatibility-approved plan as an isolated execution."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import shutil

from .artifacts import (
    ArtifactRecord, ArtifactRegistry, ArtifactResolver, RequiredArtifactMissing,
    content_sha256,
)
from .models import TaskState, now
from .persistence import ExecutionStore
from .reuse import ReuseError


class BranchExecutionError(RuntimeError):
    pass


class BranchExecutionBuilder:
    """Build a child runtime from a target workflow and explicit reuse bindings.

    The planner decides scientific equivalence and source identity.  This class
    only verifies those choices, persists child-side references, materializes
    mutable requirements safely, and lets ordinary scheduling determine
    readiness.
    """

    def _copy_target_inputs(self, workflow, child_root: Path) -> None:
        target_root = Path(workflow.root).resolve()
        for task in workflow.tasks:
            directory = child_root / task.working_directory
            directory.mkdir(parents=True, exist_ok=True)
            for filename in task.input_files:
                source = target_root / task.working_directory / filename
                if not source.is_file():
                    raise BranchExecutionError(f"Target workflow input is missing: {task.task_id}/{filename}")
                destination = directory / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        manifest = target_root / workflow.manifest_filename
        if not manifest.is_file():
            raise BranchExecutionError("Target workflow manifest is missing.")
        try:
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BranchExecutionError("Target workflow manifest is invalid.") from error
        # Generated pseudopotentials are normal execution inputs, not parent
        # scientific artifacts.  Recreate their target-relative layout in the
        # child so legacy preflight remains valid after root decoupling.
        for item in (manifest_data.get("materialized_pseudopotentials", {}) or {}).values():
            if not isinstance(item, dict):
                raise BranchExecutionError("Target pseudopotential manifest is invalid.")
            relative = str(item.get("relative_path", "")).strip()
            source = (target_root / relative).resolve()
            destination = (child_root / relative).resolve()
            if not relative or target_root not in source.parents or child_root not in destination.parents or not source.is_file():
                raise BranchExecutionError("Target materialized pseudopotential is missing or escapes its workflow.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        shutil.copy2(manifest, child_root / workflow.manifest_filename)

    @staticmethod
    def _reference_record(*, child_execution_id, source, binding):
        if source.execution_id != binding.source_execution_id:
            raise BranchExecutionError("Artifact binding source execution does not match registry record.")
        if source.producer_task_id != binding.source_task_id:
            raise BranchExecutionError("Artifact binding source task does not match registry record.")
        if source.logical_name != binding.source_logical_name or source.artifact_type != binding.source_artifact_type:
            raise BranchExecutionError("Artifact binding source logical identity/type does not match registry record.")
        source_path = Path(source.source_path).resolve()
        if not source_path.exists() or content_sha256(source_path) != source.sha256:
            raise BranchExecutionError(f"Parent artifact failed hash verification: {source.logical_name}")
        if source.sha256 != binding.source_sha256:
            raise BranchExecutionError("Artifact binding SHA does not match the registered parent artifact.")
        return ArtifactRecord(
            logical_name=binding.child_requirement_name, artifact_type=binding.child_artifact_type,
            producer_task_id="", execution_id=child_execution_id, source_path=str(source_path),
            size=source.size, sha256=source.sha256, relative_path=source.relative_path,
            origin="REFERENCE", consumer_execution_id=child_execution_id,
            source_execution_id=source.execution_id, source_task_id=source.producer_task_id,
            source_logical_name=source.logical_name, verified_sha256=source.sha256,
            materialization_policy=binding.materialization_policy,
            compatibility_fingerprint=binding.compatibility_fingerprint, verified_at=now(),
        )

    def create(self, workflow, reuse_plan, parent_record, parent_registry, *, branch_root):
        if reuse_plan.parent_execution_id != parent_record.execution_id:
            raise BranchExecutionError("Reuse plan parent does not match the supplied execution.")
        child_root = Path(branch_root).resolve()
        if child_root.exists():
            raise BranchExecutionError("Branch root already exists.")
        child_root.mkdir(parents=True)
        try:
            self._copy_target_inputs(workflow, child_root)
            child_workflow = replace(workflow, root=child_root)
            store = ExecutionStore(child_root)
            record = store.create(child_workflow)
            record.parent_execution_id = parent_record.execution_id
            record.branch_reason = reuse_plan.branch_reason
            record.reuse_plan_identity = hashlib.sha256(
                json.dumps({"evidence": reuse_plan.evidence, "artifact_bindings": [asdict(item) for item in reuse_plan.artifact_bindings]},
                           sort_keys=True, default=str).encode()
            ).hexdigest()
            record.reuse_bindings = [asdict(item) for item in reuse_plan.reusable_task_bindings] + [
                {"artifact_binding": asdict(item)} for item in reuse_plan.artifact_bindings
            ]
            record.invalidated_tasks = tuple(reuse_plan.invalidated_tasks)

            parent_artifacts = parent_registry.load()
            child_registry = ArtifactRegistry(child_root, record.execution_id)
            references = {}
            for binding in reuse_plan.artifact_bindings:
                source = parent_artifacts.get(binding.source_logical_name)
                if source is None:
                    raise BranchExecutionError(f"Parent artifact is not registered: {binding.source_logical_name}")
                parent_runtime = parent_record.tasks.get(binding.source_task_id)
                if parent_runtime is None or parent_runtime.state is not TaskState.COMPLETED:
                    raise BranchExecutionError(f"Parent producer task is not complete: {binding.source_task_id}")
                key = binding.child_requirement_name
                if key in references:
                    raise BranchExecutionError(f"Ambiguous child artifact reference: {key}")
                references[key] = self._reference_record(
                    child_execution_id=record.execution_id, source=source, binding=binding
                )
            child_registry.save(references)

            # A task is only presented as reused after every declared reusable
            # requirement for it has a verified reference in the child registry.
            task_map = child_workflow.task_map()
            for binding in reuse_plan.reusable_task_bindings:
                runtime = record.tasks.get(binding.task_id)
                if runtime is None:
                    continue
                task = task_map[binding.task_id]
                requirements = ArtifactResolver.requirements(task)
                missing = [item.logical_name for item in requirements if item.logical_name not in references]
                if missing:
                    raise BranchExecutionError(
                        f"Reusable task {binding.task_id} lacks verified artifact references: {', '.join(missing)}"
                    )
                runtime.state = TaskState.COMPLETED
                runtime.completion_origin = "REUSED_ARTIFACT"
                runtime.reused_from_execution_id = binding.source_execution_id
                runtime.reused_from_task_id = binding.source_task_id
                runtime.command_argv = []
                runtime.return_code = None
                runtime.actual_mpi_ranks = None

            # Persist a self-contained branch before materializing any mutable input.
            store.save(record)
            resolver = ArtifactResolver(child_workflow, child_registry)
            resolver.validate()
            # Materialize only newly runnable tasks whose prerequisites have been
            # satisfied by execution or verified reuse.  For Q6 this is ph.x.
            for task in child_workflow.tasks:
                runtime = record.tasks[task.task_id]
                if runtime.state is TaskState.PENDING and all(
                    record.tasks[item].state is TaskState.COMPLETED for item in task.dependencies
                ):
                    resolver.materialize(task)
            store.save(record)
            return child_workflow, record, child_registry
        except Exception:
            shutil.rmtree(child_root, ignore_errors=True)
            raise
