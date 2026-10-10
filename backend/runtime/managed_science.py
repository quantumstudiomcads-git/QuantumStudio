"""W5 managed scientific-runtime integration primitives.

This module deliberately starts *after* scientific input generation.  It
installs/verifies local Engine Pack artifacts, maps manifest-declared logical
tools to runtime POSIX paths, and transfers only declared files through the
fixed QuantumStudioRuntime agent.  It never changes a compiler, parser, or
scientific policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Iterable, Mapping, Protocol

from backend.execution.engine_family import EngineFamily
from backend.runtime.engine_pack import EnginePackManifest, EnginePackError, sha256_file, validate_engine_pack
from runtime_agent.protocol import RuntimePath
from .execution_bridge import RuntimeAgentCommandRunnerProtocol, agent_argv
from .wsl import WSLProbeError

MANAGED_ENGINE_ROOT = "/opt/quantumstudio/engines"
MANAGED_WORKFLOW_ROOT = "/var/lib/quantumstudio/workflows"
MANAGED_PSEUDO_ROOT = "/var/lib/quantumstudio/pseudopotentials"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class ManagedScienceError(RuntimeError): pass
class EnginePackIntegrityError(ManagedScienceError): pass
class EnginePackConflictError(ManagedScienceError): pass
class ArtifactTransferError(ManagedScienceError): pass
class ManagedTaskControlError(ManagedScienceError): pass


class ArtifactRole(str, Enum):
    INPUT = "INPUT"; PSEUDOPOTENTIAL = "PSEUDOPOTENTIAL"; RESTART = "RESTART"; AUXILIARY = "AUXILIARY"; CONFIGURATION = "CONFIGURATION"
    PRIMARY_OUTPUT = "PRIMARY_OUTPUT"; PARSER_INPUT = "PARSER_INPUT"; LOG = "LOG"; NUMERIC_DATA = "NUMERIC_DATA"; PROVENANCE = "PROVENANCE"; RESTART_METADATA = "RESTART_METADATA"


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ManagedScienceError(f"{label} is invalid.")
    return value


def _runtime_child(root: str, *parts: str) -> RuntimePath:
    for part in parts:
        _identifier(part, "runtime path component")
    return RuntimePath(str(PurePosixPath(root, *parts)))


def _host_under(root: Path, candidate: Path) -> Path:
    root, candidate = root.resolve(), candidate.resolve()
    if candidate != root and root not in candidate.parents:
        raise ArtifactTransferError("Host artifact path escapes the declared workflow root.")
    return candidate


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


@dataclass(frozen=True)
class EnginePackDescriptor:
    pack_id: str
    source_root: Path
    expected_manifest_sha256: str
    platform: str = "linux"
    architecture: str = "x86_64"

    def __post_init__(self) -> None:
        _identifier(self.pack_id, "engine pack id")
        if not _HEX.fullmatch(self.expected_manifest_sha256):
            raise EnginePackIntegrityError("Expected Engine Pack manifest SHA-256 is invalid.")
        object.__setattr__(self, "source_root", Path(self.source_root))


@dataclass(frozen=True)
class EnginePackInstallResult:
    pack_id: str
    version: str
    manifest_sha256: str
    installed_root: Path
    active: bool
    changed: bool
    diagnostic: str = ""


class ManagedEnginePackInstaller:
    """Offline, atomic installer for a filesystem exposed by the managed runtime.

    Production transfer to that filesystem is performed by ``ManagedRuntimeArtifactTransport``;
    this class owns the shared manifest/integrity/activation policy and is directly
    testable against a temporary mounted-runtime fixture.
    """
    marker_name = "quantumstudio-engine-packs.json"

    def __init__(self, engine_root: str | Path, *, platform: str = "linux", architecture: str = "x86_64"):
        self.engine_root = Path(engine_root)
        self.platform, self.architecture = platform, architecture

    @property
    def marker(self) -> Path: return self.engine_root / self.marker_name
    @property
    def active_path(self) -> Path: return self.engine_root / "active.json"

    def _validate_source(self, descriptor: EnginePackDescriptor) -> EnginePackManifest:
        source = descriptor.source_root.resolve()
        manifest_path = source / "engine-pack.json"
        if not manifest_path.is_file() or sha256_file(manifest_path) != descriptor.expected_manifest_sha256:
            raise EnginePackIntegrityError("Engine Pack manifest SHA-256 does not match the declared artifact.")
        validation = validate_engine_pack(source, platform_name=descriptor.platform, architecture=descriptor.architecture)
        if not validation.valid:
            raise EnginePackIntegrityError("Engine Pack source validation failed: " + ", ".join((*validation.missing, *validation.mismatched, *validation.warnings)))
        try: return EnginePackManifest.load(manifest_path)
        except (OSError, ValueError, KeyError, EnginePackError) as error: raise EnginePackIntegrityError("Engine Pack manifest is invalid.") from error

    def _assert_owned_root(self) -> None:
        if not self.engine_root.exists():
            self.engine_root.mkdir(parents=True, exist_ok=True)
            _atomic_json(self.marker, {"schema_version": 1, "owner": "QuantumStudio", "kind": "managed-engine-packs"})
            return
        if not self.marker.is_file():
            if any(self.engine_root.iterdir()):
                raise EnginePackConflictError("Managed Engine Pack root contains unknown content.")
            _atomic_json(self.marker, {"schema_version": 1, "owner": "QuantumStudio", "kind": "managed-engine-packs"})
            return
        try: marker = json.loads(self.marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error: raise EnginePackConflictError("Managed Engine Pack ownership marker is invalid.") from error
        if marker.get("owner") != "QuantumStudio" or marker.get("kind") != "managed-engine-packs":
            raise EnginePackConflictError("Managed Engine Pack root is not owned by Quantum Studio.")

    def _active(self) -> dict[str, object] | None:
        try:
            value = json.loads(self.active_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except FileNotFoundError: return None
        except (OSError, json.JSONDecodeError) as error: raise EnginePackConflictError("Active Engine Pack metadata is invalid.") from error

    @staticmethod
    def _version_key(value: str) -> tuple[object, ...]:
        return tuple(int(part) if part.isdigit() else part for part in re.split(r"([0-9]+)", value))

    def install(self, descriptor: EnginePackDescriptor) -> EnginePackInstallResult:
        manifest = self._validate_source(descriptor)
        self._assert_owned_root()
        version = _identifier(manifest.engine_pack_version, "engine pack version")
        packs = self.engine_root / "packs"; packs.mkdir(exist_ok=True)
        target = packs / f"{descriptor.pack_id}-{version}"
        existing_active = self._active()
        if existing_active and existing_active.get("pack_id") == descriptor.pack_id and self._version_key(version) < self._version_key(str(existing_active.get("version", ""))):
            raise EnginePackConflictError("Refusing to downgrade the active managed Engine Pack.")
        if target.exists():
            digest = sha256_file(target / "engine-pack.json") if (target / "engine-pack.json").is_file() else ""
            if digest != descriptor.expected_manifest_sha256:
                raise EnginePackConflictError("Same Engine Pack version has conflicting manifest identity.")
            validation = validate_engine_pack(target, platform_name=descriptor.platform, architecture=descriptor.architecture)
            if not validation.valid: raise EnginePackIntegrityError("Existing Engine Pack failed verification.")
            changed = False
        else:
            staging = packs / ("." + target.name + ".staging")
            if staging.exists(): raise EnginePackConflictError("Managed Engine Pack staging location already exists.")
            try:
                for item in descriptor.source_root.rglob("*"):
                    relative = item.relative_to(descriptor.source_root)
                    destination = staging / relative
                    if item.is_symlink(): raise EnginePackIntegrityError("Engine Pack source may not contain symlinks.")
                    if item.is_dir(): destination.mkdir(parents=True, exist_ok=True)
                    elif item.is_file(): destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(item, destination)
                validation = validate_engine_pack(staging, platform_name=descriptor.platform, architecture=descriptor.architecture)
                if not validation.valid or sha256_file(staging / "engine-pack.json") != descriptor.expected_manifest_sha256:
                    raise EnginePackIntegrityError("Staged Engine Pack verification failed.")
                os.replace(staging, target); changed = True
            except Exception:
                if staging.exists(): shutil.rmtree(staging)
                raise
        active = {"schema_version": 1, "pack_id": descriptor.pack_id, "version": version,
                  "manifest_sha256": descriptor.expected_manifest_sha256, "relative_root": str(target.relative_to(self.engine_root))}
        if existing_active != active: _atomic_json(self.active_path, active); changed = True
        return EnginePackInstallResult(descriptor.pack_id, version, descriptor.expected_manifest_sha256, target, True, changed)


@dataclass(frozen=True)
class ManagedEngineFamily:
    """Verified logical tool mapping to absolute paths in the runtime namespace."""
    manifest_sha256: str
    pack_id: str
    version: str
    runtime_root: RuntimePath
    tools: Mapping[str, RuntimePath]
    tool_sha256: Mapping[str, str]
    family: EngineFamily

    def resolve(self, tool_id: str) -> RuntimePath:
        try: return self.tools[tool_id]
        except KeyError as error: raise EnginePackIntegrityError(f"Verified managed Engine Pack lacks required tool {tool_id!r}.") from error


def discover_managed_engine_family(installed_root: str | Path, *, pack_id: str, runtime_root: str = MANAGED_ENGINE_ROOT,
                                   platform: str = "linux", architecture: str = "x86_64") -> ManagedEngineFamily:
    root = Path(installed_root).resolve()
    validation = validate_engine_pack(root, platform_name=platform, architecture=architecture)
    if not validation.valid: raise EnginePackIntegrityError("Managed Engine Pack is not verified.")
    manifest_file = root / "engine-pack.json"; raw = json.loads(manifest_file.read_text(encoding="utf-8")); manifest = EnginePackManifest.load(manifest_file)
    tools: dict[str, RuntimePath] = {}; hashes: dict[str, str] = {}
    for item in manifest.engines:
        logical = str(item.get("tool_id") or item.get("executable") or "")
        relative = str(item.get("relative_path") or "")
        if not logical or not relative or logical in tools: raise EnginePackIntegrityError("Engine Pack tool mapping is malformed.")
        runtime_path = RuntimePath(str(PurePosixPath(runtime_root, "packs", f"{pack_id}-{manifest.engine_pack_version}", relative)))
        tools[logical] = runtime_path; hashes[logical] = str(item.get("sha256", ""))
    family = EngineFamily(str(raw.get("family", "MANAGED_ENGINE_PACK")), str(RuntimePath(runtime_root)),
                          {name: str(path) for name, path in tools.items()}, str(raw.get("qe_version", "")),
                          str(raw.get("epw_version", "")), str(raw.get("wannier_version", "")))
    return ManagedEngineFamily(sha256_file(manifest_file), pack_id, manifest.engine_pack_version,
                               RuntimePath(runtime_root), tools, hashes, family)


@dataclass(frozen=True)
class StageInArtifact:
    host_source: Path
    runtime_destination: RuntimePath
    role: ArtifactRole
    required: bool = True
    sha256: str = ""
    mutable: bool = False
    provenance: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "host_source", Path(self.host_source))
        if self.sha256 and not _HEX.fullmatch(self.sha256): raise ArtifactTransferError("Declared artifact SHA-256 is invalid.")


@dataclass(frozen=True)
class StageOutArtifact:
    runtime_source: RuntimePath
    host_destination: Path
    role: ArtifactRole
    required: bool = True
    capture_sha256: bool = True
    retain_runtime_copy: bool = True

    def __post_init__(self) -> None: object.__setattr__(self, "host_destination", Path(self.host_destination))


@dataclass(frozen=True)
class RuntimeArtifactReference:
    runtime_id: str
    workflow_id: str
    execution_id: str
    role: ArtifactRole
    runtime_path: RuntimePath
    size: int
    sha256: str = ""
    engine_family_identity: str = ""


class ManagedRuntimeArtifactTransport:
    """Fixed-agent, streaming transfer control plane; never translates host paths."""
    def __init__(self, runner: RuntimeAgentCommandRunnerProtocol, *, timeout: float | None = None): self.runner, self.timeout = runner, timeout

    @staticmethod
    def _result_ok(result) -> None:
        if result.error is WSLProbeError.TIMEOUT: raise ArtifactTransferError("Managed artifact transport timed out.")
        if result.error is not None or result.returncode != 0: raise ArtifactTransferError(result.error_message or "Managed artifact transport failed.")

    def stage_in(self, artifact: StageInArtifact) -> dict[str, object]:
        source = artifact.host_source.resolve()
        if not source.is_file():
            if artifact.required: raise ArtifactTransferError("Required stage-in source is missing.")
            return {"status": "OPTIONAL_MISSING"}
        digest = sha256_file(source)
        if artifact.sha256 and digest != artifact.sha256: raise ArtifactTransferError("Stage-in source SHA-256 does not match declared identity.")
        header = {"schema_version": 1, "operation": "stage_in", "destination": str(artifact.runtime_destination), "sha256": digest}
        runner = self.runner
        if not hasattr(runner, "run_with_streaming_input"): raise ArtifactTransferError("WSL transport does not support streamed stage-in.")
        result = runner.run_with_streaming_input(agent_argv("stage-in"), (json.dumps(header, separators=(",", ":")) + "\n").encode("utf-8"), str(source), timeout=self.timeout)
        self._result_ok(result)
        try: value = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ArtifactTransferError("Managed stage-in response is malformed.") from error
        if value.get("sha256") != digest: raise ArtifactTransferError("Managed stage-in did not preserve artifact identity.")
        return value

    def stage_out(self, artifact: StageOutArtifact, *, host_root: str | Path) -> RuntimeArtifactReference | None:
        destination = _host_under(Path(host_root), artifact.host_destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".qs-stage.tmp")
        request = {"schema_version": 1, "operation": "stage_out", "source": str(artifact.runtime_source)}
        runner = self.runner
        if not hasattr(runner, "run_with_streaming_output"): raise ArtifactTransferError("WSL transport does not support streamed stage-out.")
        try:
            result = runner.run_with_streaming_output(agent_argv("stage-out"), json.dumps(request, separators=(",", ":")).encode("utf-8"), str(temporary), timeout=self.timeout)
            if result.error is not None or result.returncode != 0:
                if artifact.required: self._result_ok(result)
                return None
            digest = sha256_file(temporary) if artifact.capture_sha256 else ""; size = temporary.stat().st_size
            os.replace(temporary, destination)
            return RuntimeArtifactReference("QuantumStudioRuntime", "", "", artifact.role, artifact.runtime_source, size, digest)
        finally:
            try: temporary.unlink()
            except OSError: pass

    def task_status(self, task_id: str) -> dict[str, object]:
        _identifier(task_id, "task id")
        result = self.runner.run_with_input(agent_argv("status"), json.dumps({"schema_version": 1, "task_id": task_id}).encode("utf-8"), timeout=10.0)
        self._result_ok(result)
        try: return json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ManagedTaskControlError("Managed task status response is malformed.") from error

    def cancel(self, task_id: str, *, grace_seconds: float = 2.0) -> dict[str, object]:
        _identifier(task_id, "task id")
        result = self.runner.run_with_input(agent_argv("cancel"), json.dumps({"schema_version": 1, "task_id": task_id, "grace_seconds": float(grace_seconds)}).encode("utf-8"), timeout=10.0 + grace_seconds)
        self._result_ok(result)
        try: return json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ManagedTaskControlError("Managed task cancellation response is malformed.") from error


def managed_execution_directory(workflow_id: str, execution_id: str, task_id: str) -> RuntimePath:
    return _runtime_child(MANAGED_WORKFLOW_ROOT, _identifier(workflow_id, "workflow id"), "executions", _identifier(execution_id, "execution id"), _identifier(task_id, "task id"))


def _runtime_relative(directory: RuntimePath, relative: str) -> RuntimePath:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        raise ArtifactTransferError("Runtime artifact relative path is invalid.")
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ArtifactTransferError("Runtime artifact relative path escapes its task directory.")
    return RuntimePath(str(PurePosixPath(str(directory), candidate)))


def _managed_task_outcome(status_payload: object, process_return_code: int | None = None,
                          expected_task_id: str | None = None) -> tuple[str, str, int | None]:
    """Translate authoritative agent state without making unknown work retryable."""
    payload = status_payload if isinstance(status_payload, dict) else {}
    record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
    if expected_task_id is not None and (payload.get("task_id") != expected_task_id
                                         or record.get("task_id") != expected_task_id):
        return "INDETERMINATE", "task_control_identity_unproven", process_return_code
    code = record.get("return_code", payload.get("return_code"))
    if (type(code) is int and type(process_return_code) is int and code != process_return_code):
        return "INDETERMINATE", "task_return_code_mismatch", process_return_code
    if type(code) is not int:
        code = process_return_code if type(process_return_code) is int else None
    failure = record.get("failure_code", payload.get("failure_code"))
    status = payload.get("status")
    if status == "TASK_CANCELLATION_INDETERMINATE":
        return "INDETERMINATE", str(failure or "cancellation_action_outcome_unproven"), code
    if status == "TASK_OUTCOME_INDETERMINATE":
        return "INDETERMINATE", str(failure or "task_exit_outcome_unproven"), code
    if status == "TASK_CANCELLED":
        return "CANCELLED", "", code
    if status == "TASK_FAILED":
        return "FAILED", str(failure or "EXECUTION_FAILED"), code
    if status == "TASK_FINISHED" and record.get("state") == "FINISHED" and code is not None:
        return ("COMPLETED" if code == 0 else "FAILED"), ("" if code == 0 else "EXECUTION_FAILED"), code
    if status == "TASK_RUNNING" and process_return_code is None:
        return "RUNNING", "", code
    return "INDETERMINATE", "task_control_outcome_unproven", code


class ManagedScientificExecutionService:
    required_agent_capabilities = frozenset({"run", "stage_in", "stage_out", "status", "cancel"})

    """Small generated-workflow adapter that begins after compiler generation.

    It deliberately supports only manifest-verified subprocess tools.  Local
    Linux and internal/Python execution modes keep using their existing paths.
    Results are parsed only after declared files have returned to the host.
    """
    def __init__(self, runtime, engine_family: ManagedEngineFamily, transport: ManagedRuntimeArtifactTransport):
        self.runtime, self.engine_family, self.transport = runtime, engine_family, transport

    def resolve_executable(self, tool_id: str, program: str, engine_id: str | None = None) -> RuntimePath:
        # ``tool_id`` is the logical identity produced by the existing planner;
        # ``program`` is checked only as an equal declaration, never searched.
        path = self.engine_family.resolve(tool_id)
        if program not in {tool_id, Path(str(path)).name}:
            raise EnginePackIntegrityError("Generated command does not match the verified logical tool identity.")
        return path

    def execute(self, workflow, *, record=None, store=None, result_service=None):
        from backend.core.execution_contract import ExecutionMode
        from backend.execution.models import TaskExecutionRecord, TaskState, WorkflowExecutionRecord, now
        from backend.execution.errors import ExecutionPreflightError

        health = self.runtime._require_execution_ready()
        if not self.required_agent_capabilities.issubset(set(health.capabilities)):
            raise ManagedScienceError("QuantumStudioRuntime agent lacks required W5 capabilities.")
        root = Path(workflow.root).resolve()
        if not root.is_dir(): raise ExecutionPreflightError("Generated workflow root does not exist.")
        execution_id = (record.execution_id if record else "") or "managed-" + _identifier(workflow.request_id, "workflow id")
        records = record.tasks if record is not None else {task.task_id: TaskExecutionRecord(task.task_id) for task in workflow.tasks}
        record = record or WorkflowExecutionRecord(workflow.request_id, str(root), records, execution_id=execution_id)
        if any(item.state in {TaskState.INDETERMINATE, TaskState.CANCELLED} for item in records.values()):
            raise ManagedTaskControlError("Indeterminate or cancelled managed execution is terminal; it cannot resume.")
        record.started_at = record.started_at or now(); record.provider_provenance.update(self.runtime.runtime_provenance())
        for task in workflow.tasks:
            item = records[task.task_id]
            if item.state is TaskState.COMPLETED: continue
            if any(records[dependency].state is not TaskState.COMPLETED for dependency in task.dependencies):
                item.state = TaskState.BLOCKED; item.error_type = "BLOCKED"; item.error_message = "Blocked by prerequisite."; item.finished_at = now(); continue
            if task.command.execution_mode is not ExecutionMode.SUBPROCESS:
                item.state = TaskState.BLOCKED; item.error_type = "UNSUPPORTED_MANAGED_EXECUTION_MODE"; item.error_message = "Task execution mode remains host-native or unselected."; item.finished_at = now(); continue
            runtime_dir = managed_execution_directory(workflow.request_id, execution_id, task.task_id)
            try:
                executable = self.resolve_executable(task.tool_id, task.command.program, task.engine_id)
                for filename in task.input_files:
                    source = _host_under(root, root / task.working_directory / filename)
                    destination = _runtime_relative(runtime_dir, filename)
                    self.transport.stage_in(StageInArtifact(source, destination, ArtifactRole.INPUT, sha256=sha256_file(source)))
                stdin_path = _runtime_relative(runtime_dir, task.command.stdin_file) if task.command.stdin_file else None
                stdout_name, stderr_name = task.command.stdout_file or "stdout.log", task.command.stderr_file or "stderr.log"
                stdout_path, stderr_path = _runtime_relative(runtime_dir, stdout_name), _runtime_relative(runtime_dir, stderr_name)
                from runtime_agent.protocol import RuntimeProcessRequest
                request = RuntimeProcessRequest(task.task_id, executable, tuple(task.command.arguments), runtime_dir,
                                                dict(task.command.environment), stdin_path, stdout_path, stderr_path,
                                                task.timeout_seconds)
                item.state = TaskState.RUNNING; item.started_at = now(); item.error_type = ""; item.error_message = ""
                item.resolved_executable = str(executable); item.command_argv = [str(executable), *task.command.arguments]
                bridge = self.runtime.execute_runtime_task(request, record=record)
                process = bridge.process
                if process is None or not process.started:
                    item.state = TaskState.FAILED; item.error_type = "WSL_TRANSPORT_FAILED"; item.error_message = bridge.diagnostic
                else:
                    item.process_id = process.runtime_pid; item.return_code = process.return_code
                    try:
                        authoritative = self.transport.task_status(task.task_id)
                    except (ManagedScienceError, OSError, ValueError, TypeError):
                        authoritative = {"status": "TASK_OUTCOME_INDETERMINATE",
                                         "failure_code": "task_control_outcome_unproven"}
                    state, failure, code = _managed_task_outcome(authoritative, process.return_code,
                                                                 expected_task_id=task.task_id)
                    item.state = TaskState(state)
                    item.return_code = code
                    if item.state is TaskState.INDETERMINATE:
                        item.error_type = failure
                        item.error_message = "Managed task outcome is unproven; operator review is required."
                    elif item.state is TaskState.FAILED:
                        item.error_type = failure
                        item.error_message = process.diagnostic or f"Process exited with code {code}."
                    elif item.state is TaskState.CANCELLED:
                        item.error_message = "Managed task cancellation was confirmed."
                    item.stdout_path = str(root / task.working_directory / stdout_name); item.stderr_path = str(root / task.working_directory / stderr_name)
                    try:
                        self.transport.stage_out(StageOutArtifact(stdout_path, Path(item.stdout_path), ArtifactRole.LOG, required=False), host_root=root)
                        self.transport.stage_out(StageOutArtifact(stderr_path, Path(item.stderr_path), ArtifactRole.LOG, required=False), host_root=root)
                        for output in task.artifact_outputs:
                            runtime_output = _runtime_relative(runtime_dir, output)
                            self.transport.stage_out(StageOutArtifact(runtime_output, root / task.working_directory / output, ArtifactRole.PARSER_INPUT, required=False), host_root=root)
                    except (ManagedScienceError, OSError) as stage_error:
                        if item.state not in {TaskState.INDETERMINATE, TaskState.CANCELLED}:
                            item.state = TaskState.FAILED
                            item.error_type = "STAGING_FAILED"
                            item.error_message = str(stage_error)
            except (ManagedScienceError, OSError, ExecutionPreflightError) as error:
                item.state = TaskState.FAILED; item.error_type = "STAGING_FAILED"; item.error_message = str(error)
            item.finished_at = now()
            if store: store.save(record)
        record.finished_at = now()
        if store: store.save(record)
        # The service receives only the host root; runtime POSIX paths are never
        # passed across this boundary. Parser failures remain ResultStatus state.
        if result_service is not None and all(item.state is TaskState.COMPLETED for item in records.values()):
            result_service.parse(root, execution_id)
        return record

    def cancel(self, task_id: str) -> dict[str, object]:
        return self.transport.cancel(task_id)

    def recover_running(self, task_id: str) -> dict[str, object]:
        try:
            payload = self.transport.task_status(task_id)
        except (ManagedScienceError, OSError, ValueError, TypeError):
            payload = {"status": "TASK_OUTCOME_INDETERMINATE",
                       "failure_code": "task_control_outcome_unproven"}
        state, failure, code = _managed_task_outcome(payload, expected_task_id=task_id)
        return {"state": state, "failure_code": failure or None, "return_code": code,
                "diagnostic": ("Operator review is required before any new attempt."
                               if state == "INDETERMINATE" else "")}


class ManagedEnginePackDeployment:
    """Deploy a verified local artifact through the fixed runtime-agent endpoint.

    It has no distro parameter and no host-path translation. Every source file
    is streamed to the agent's fixed engine staging root before the agent
    performs its independent staged verification and activation.
    """
    def __init__(self, transport: ManagedRuntimeArtifactTransport, *, platform: str = "linux", architecture: str = "x86_64"):
        self.transport, self.platform, self.architecture = transport, platform, architecture

    def install(self, descriptor: EnginePackDescriptor) -> dict[str, object]:
        verifier = ManagedEnginePackInstaller(Path("."), platform=self.platform, architecture=self.architecture)
        manifest = verifier._validate_source(descriptor)
        version = _identifier(manifest.engine_pack_version, "engine pack version")
        stage_root = RuntimePath(str(PurePosixPath(MANAGED_ENGINE_ROOT, ".staging", f"{descriptor.pack_id}-{version}")))
        for source in sorted(descriptor.source_root.rglob("*")):
            if source.is_dir(): continue
            if source.is_symlink(): raise EnginePackIntegrityError("Engine Pack source may not contain symlinks.")
            relative = source.relative_to(descriptor.source_root)
            if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
                raise EnginePackIntegrityError("Engine Pack source path is invalid.")
            destination = RuntimePath(str(PurePosixPath(str(stage_root), *relative.parts)))
            self.transport.stage_in(StageInArtifact(source, destination, ArtifactRole.CONFIGURATION,
                                                    sha256=sha256_file(source)))
        request = {"schema_version": 1, "operation": "install_engine_pack", "pack_id": descriptor.pack_id,
                   "version": version, "manifest_sha256": descriptor.expected_manifest_sha256}
        result = self.transport.runner.run_with_input(agent_argv("install-engine-pack"),
                                                       json.dumps(request, separators=(",", ":")).encode("utf-8"), timeout=30.0)
        self.transport._result_ok(result)
        try: response = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error: raise EnginePackIntegrityError("Managed Engine Pack activation response is malformed.") from error
        if response.get("status") != "ACTIVATED" or response.get("manifest_sha256") != descriptor.expected_manifest_sha256:
            raise EnginePackIntegrityError("Managed Engine Pack activation was not verified.")
        return response
