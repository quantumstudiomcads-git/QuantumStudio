"""Versioned, atomic execution-sidecar persistence and recovery (C7)."""
from __future__ import annotations

from dataclasses import asdict
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import threading
import uuid

from .models import TaskExecutionRecord, TaskState, WorkflowExecutionRecord, now
from .recovery import recover_stale_running

SCHEMA_VERSION = "0.1"


class RecoveryState(str, Enum):
    NEVER_RUN = "NEVER_RUN"
    RECOVERABLE = "RECOVERABLE"
    COMPLETE = "COMPLETE"
    INCOMPATIBLE = "INCOMPATIBLE"
    CORRUPT_RUNTIME_RECORD = "CORRUPT_RUNTIME_RECORD"
    MISSING_WORKFLOW = "MISSING_WORKFLOW"
    MODIFIED_INPUTS = "MODIFIED_INPUTS"


class ExecutionStoreError(RuntimeError):
    pass


class RecoveryAssessment:
    def __init__(self, state, message="", record=None):
        self.state, self.message, self.record = RecoveryState(state), message, record


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def workflow_fingerprint(workflow) -> tuple[str, dict[str, str], str]:
    root = Path(workflow.root).resolve()
    manifest = root / workflow.manifest_filename
    if not manifest.is_file():
        raise ExecutionStoreError("Generated workflow manifest is missing.")
    inputs = {}
    tasks = []
    for task in workflow.tasks:
        task_inputs = []
        for filename in task.input_files:
            path = (root / task.working_directory / filename).resolve()
            if root not in path.parents:
                raise ExecutionStoreError("Generated input path escapes workflow root.")
            if not path.is_file():
                raise ExecutionStoreError(f"Generated input is missing: {filename}")
            digest = _sha256(path)
            inputs[f"{task.task_id}/{filename}"] = digest
            task_inputs.append((filename, digest))
        tasks.append((task.task_id, task.semantic_task_type, task.engine_id, task.tool_id,
                      task.dependencies, task.working_directory, tuple(task_inputs)))
    payload = json.dumps({"manifest": _sha256(manifest), "tasks": tasks}, sort_keys=True, default=list).encode()
    return hashlib.sha256(payload).hexdigest(), inputs, _sha256(manifest)


class ExecutionStore:
    """Stores runtime data under ``<workflow>/executions/<execution-id>/`` only."""
    def __init__(self, workflow_root):
        self.root = Path(workflow_root).resolve()
        self.executions = self.root / "executions"
        self._lock = threading.RLock()

    def _safe(self, execution_id: str) -> Path:
        path = (self.executions / execution_id / "execution.json").resolve()
        if self.root not in path.parents:
            raise ExecutionStoreError("Execution sidecar path escapes workflow root.")
        return path

    def create(self, workflow, *, request_fingerprint="", structure_fingerprint=""):
        fingerprint, inputs, manifest = workflow_fingerprint(workflow)
        execution_id = uuid.uuid4().hex
        tasks = {task.task_id: TaskExecutionRecord(task.task_id) for task in workflow.tasks}
        record = WorkflowExecutionRecord(workflow.request_id, str(self.root), tasks,
            execution_id=execution_id, workflow_fingerprint=fingerprint,
            manifest_fingerprint=manifest, input_fingerprints=inputs,
            request_fingerprint=request_fingerprint, structure_fingerprint=structure_fingerprint,
            created_at=now())
        self.save(record)
        return record

    def _payload(self, record):
        return {
            "execution_schema_version": SCHEMA_VERSION, "execution_id": record.execution_id,
            "request_id": record.request_id, "request_fingerprint": record.request_fingerprint, "parent_execution_id": record.parent_execution_id, "branch_reason": record.branch_reason, "reuse_plan_identity": record.reuse_plan_identity, "reuse_bindings": record.reuse_bindings, "invalidated_tasks": list(record.invalidated_tasks),
            "structure_fingerprint": record.structure_fingerprint,
            "workflow_manifest_fingerprint": record.manifest_fingerprint,
            "workflow_fingerprint": record.workflow_fingerprint, "workflow_root": record.workflow_root,
            "created_at": record.created_at, "started_at": record.started_at,
            "updated_at": now(), "finished_at": record.finished_at, "state": record.state.value,
            "input_fingerprints": record.input_fingerprints,
            "tasks": {key: {**asdict(value), "state": value.state.value} for key, value in record.tasks.items()},
        }

    def save(self, record):
        if not record.execution_id:
            raise ExecutionStoreError("Execution record has no execution identity.")
        with self._lock:
            path = self._safe(record.execution_id); path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            encoded = json.dumps(self._payload(record), indent=2, sort_keys=True) + "\n"
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
            try:
                directory = os.open(str(path.parent), os.O_DIRECTORY)
                try: os.fsync(directory)
                finally: os.close(directory)
            except (AttributeError, OSError):
                pass

    def load(self, execution_id):
        path = self._safe(execution_id)
        try: data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError: raise ExecutionStoreError("Execution sidecar is missing.")
        except (OSError, json.JSONDecodeError): raise ExecutionStoreError("Execution sidecar is corrupt.")
        if data.get("execution_schema_version") != SCHEMA_VERSION:
            raise ExecutionStoreError("Execution sidecar schema is incompatible.")
        tasks = {}
        try:
            for task_id, item in data["tasks"].items():
                item = dict(item); item["state"] = TaskState(item["state"]); tasks[task_id] = TaskExecutionRecord(**item)
        except (KeyError, TypeError, ValueError):
            raise ExecutionStoreError("Execution sidecar task data is corrupt.")
        return WorkflowExecutionRecord(data["request_id"], data["workflow_root"], tasks,
            execution_id=data["execution_id"], request_fingerprint=data.get("request_fingerprint", ""),
            structure_fingerprint=data.get("structure_fingerprint", ""), workflow_fingerprint=data.get("workflow_fingerprint", ""),
            manifest_fingerprint=data.get("workflow_manifest_fingerprint", ""), input_fingerprints=data.get("input_fingerprints", {}),
            created_at=data.get("created_at"), started_at=data.get("started_at"), finished_at=data.get("finished_at"), parent_execution_id=data.get("parent_execution_id", ""), branch_reason=data.get("branch_reason", ""), reuse_plan_identity=data.get("reuse_plan_identity", ""), reuse_bindings=data.get("reuse_bindings", []), invalidated_tasks=tuple(data.get("invalidated_tasks", ())))

    def list(self):
        if not self.executions.is_dir(): return ()
        return tuple(sorted(path.parent.name for path in self.executions.glob("*/execution.json")))

    def assess(self, workflow, execution_id=None, *, request_id=None, request_fingerprint=""):
        if not self.root.is_dir() or not (self.root / workflow.manifest_filename).is_file():
            return RecoveryAssessment(RecoveryState.MISSING_WORKFLOW, "Generated workflow is missing.")
        ids = self.list()
        if not ids: return RecoveryAssessment(RecoveryState.NEVER_RUN, "No execution sidecar exists.")
        try: record = self.load(execution_id or ids[-1])
        except ExecutionStoreError as error: return RecoveryAssessment(RecoveryState.CORRUPT_RUNTIME_RECORD, str(error))
        if Path(record.workflow_root).resolve() != self.root:
            return RecoveryAssessment(RecoveryState.INCOMPATIBLE, "Execution workspace root changed.", record)
        if (request_id and record.request_id != request_id) or (request_fingerprint and record.request_fingerprint and record.request_fingerprint != request_fingerprint):
            return RecoveryAssessment(RecoveryState.INCOMPATIBLE, "Execution belongs to another request.", record)
        try: fingerprint, inputs, manifest = workflow_fingerprint(workflow)
        except ExecutionStoreError as error: return RecoveryAssessment(RecoveryState.MISSING_WORKFLOW, str(error), record)
        if record.workflow_fingerprint != fingerprint or record.manifest_fingerprint != manifest:
            return RecoveryAssessment(RecoveryState.INCOMPATIBLE, "Generated workflow manifest changed.", record)
        if record.input_fingerprints != inputs:
            return RecoveryAssessment(RecoveryState.MODIFIED_INPUTS, "Generated scientific inputs changed.", record)
        changed = recover_stale_running(record)
        for runtime in record.tasks.values():
            if runtime.stdout_path and self.root not in Path(runtime.stdout_path).resolve().parents:
                runtime.state = TaskState.FAILED; runtime.error_message = "Runtime log path escapes workflow root."; changed = True
            elif runtime.state is TaskState.COMPLETED and (not runtime.stdout_path or not Path(runtime.stdout_path).is_file()):
                runtime.state = TaskState.FAILED; runtime.error_message = "Completed task log is unavailable."; changed = True
        if changed: self.save(record)
        state = RecoveryState.COMPLETE if record.state.value == "COMPLETED" else RecoveryState.RECOVERABLE
        return RecoveryAssessment(state, "Execution record is valid.", record)

    def invalidate_downstream(self, workflow, record, task_id):
        descendants = {task_id}; changed = True
        while changed:
            changed = False
            for task in workflow.tasks:
                if task.task_id not in descendants and any(dep in descendants for dep in task.dependencies):
                    descendants.add(task.task_id); changed = True
        for item in descendants:
            runtime = record.tasks[item]
            runtime.state = TaskState.PENDING; runtime.error_message = ""; runtime.return_code = None; runtime.finished_at = None
        self.save(record); return descendants
