"""Compute-runtime boundary; scientific code remains provider-independent."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.runtime.managed import ManagedRuntimeIdentity, RuntimeState, RuntimeType
from backend.runtime.platform import OperatingSystem, PlatformInfo, current_platform
from backend.runtime.wsl import WSLHealthReport, WSLRuntimeState
from backend.runtime.provisioning import ManagedRuntimeHealthState
from backend.runtime.execution_bridge import ManagedRuntimeExecutionBridge, RuntimeBridgeHealth
from runtime_agent.protocol import RuntimeProcessRequest
from .errors import ExecutionPreflightError
from .local import LocalExecutionManager
from .tools import LocalToolConfiguration


@dataclass(frozen=True)
class RuntimeProbe:
    state: RuntimeState
    message: str


class ComputeRuntime:
    """Minimal execution-provider contract, deliberately independent of Qt and science."""
    identity: ManagedRuntimeIdentity

    def probe(self) -> RuntimeProbe:
        raise NotImplementedError

    def resolve_executable(self, tool_id: str, program: str, engine_id: str | None = None) -> Path:
        raise NotImplementedError

    def execute(self, workflow: Any, record=None, store=None):
        raise NotImplementedError

    def cancel(self) -> None:
        raise NotImplementedError


class LocalLinuxRuntime(ComputeRuntime):
    """Thin adapter over the proven LocalExecutionManager; no execution semantics are duplicated."""
    def __init__(self, tools: LocalToolConfiguration | None = None, info: PlatformInfo | None = None):
        self.info = info or current_platform()
        self.identity = ManagedRuntimeIdentity.local_linux(self.info)
        self.manager = LocalExecutionManager(tools or LocalToolConfiguration())

    def probe(self) -> RuntimeProbe:
        if self.info.operating_system is not OperatingSystem.LINUX:
            return RuntimeProbe(RuntimeState.INVALID, "LocalLinuxRuntime requires a Linux host.")
        return RuntimeProbe(RuntimeState.READY, "Existing local Linux execution manager is available.")

    def resolve_executable(self, tool_id, program, engine_id=None):
        return self.manager.tools.resolve(tool_id, program, engine_id)

    def execute(self, workflow, record=None, store=None):
        return self.manager.execute(workflow, record=record, store=store)

    def cancel(self):
        self.manager.cancel()


class ManagedWSL2Runtime(ComputeRuntime):
    """Managed WSL2 provider with a runtime-local, agent-mediated task primitive.

    It deliberately cannot execute an ordinary host GeneratedWorkflow yet: W5
    owns staging and artifact collection.  It can only submit already-runtime-
    local ``RuntimeProcessRequest`` objects through the fixed agent transport.
    """
    def __init__(self, info: PlatformInfo | None = None, health_report: WSLHealthReport | None = None,
                 provisioning_health: ManagedRuntimeHealthState | None = None,
                 agent_bridge: ManagedRuntimeExecutionBridge | None = None,
                 agent_health: RuntimeBridgeHealth | None = None,
                 runtime_version: str = "", architecture: str = "x86_64"):
        self.info = info or current_platform()
        self.identity = ManagedRuntimeIdentity.managed_wsl2(self.info)
        self.health_report = health_report
        self.provisioning_health = provisioning_health
        self.agent_bridge = agent_bridge
        self.agent_health = agent_health
        self.runtime_version = runtime_version
        self.runtime_architecture = architecture

    def _agent_health(self) -> RuntimeBridgeHealth | None:
        if self.agent_health is not None:
            return self.agent_health
        return self.agent_bridge.probe_agent() if self.agent_bridge is not None else None

    def probe(self) -> RuntimeProbe:
        if self.info.operating_system is not OperatingSystem.WINDOWS:
            return RuntimeProbe(RuntimeState.INVALID, "ManagedWSL2Runtime requires a Windows host.")
        if not self.health_report or self.health_report.managed_runtime.health_state is not WSLRuntimeState.REGISTERED_WSL2:
            return RuntimeProbe(RuntimeState.AVAILABLE_NOT_READY, "QuantumStudioRuntime is not registered as the required WSL2 distribution.")
        if self.provisioning_health is not ManagedRuntimeHealthState.METADATA_VALID:
            return RuntimeProbe(RuntimeState.AVAILABLE_NOT_READY, "QuantumStudioRuntime metadata is not verified.")
        health = self._agent_health()
        if health is None or not health.ready:
            return RuntimeProbe(RuntimeState.AVAILABLE_NOT_READY, "QuantumStudioRuntime agent is unavailable or incompatible.")
        return RuntimeProbe(RuntimeState.AVAILABLE_NOT_READY, "Runtime execution bridge is ready; scientific Engine Pack readiness is still unavailable.")

    def _require_execution_ready(self) -> RuntimeBridgeHealth:
        if self.info.operating_system is not OperatingSystem.WINDOWS:
            raise ExecutionPreflightError("Managed WSL2 execution requires a Windows host.")
        if not self.health_report or self.health_report.managed_runtime.health_state is not WSLRuntimeState.REGISTERED_WSL2:
            raise ExecutionPreflightError("QuantumStudioRuntime is not registered as WSL2.")
        if self.provisioning_health is not ManagedRuntimeHealthState.METADATA_VALID:
            raise ExecutionPreflightError("QuantumStudioRuntime metadata is not verified.")
        if self.agent_bridge is None:
            raise ExecutionPreflightError("Managed runtime-agent transport is unavailable.")
        health = self._agent_health()
        if health is None or not health.ready:
            raise ExecutionPreflightError("QuantumStudioRuntime agent is unavailable or incompatible.")
        return health

    def runtime_provenance(self, agent_health: RuntimeBridgeHealth | None = None) -> dict:
        health = agent_health or self._agent_health()
        return ManagedRuntimeExecutionBridge.provenance(runtime_version=self.runtime_version,
                                                        architecture=self.runtime_architecture,
                                                        agent_version=health.agent_version if health and health.ready else "")

    def execute_runtime_task(self, request: RuntimeProcessRequest, *, record=None):
        health = self._require_execution_ready()
        result = self.agent_bridge.execute(request)
        if record is not None:
            record.provider_provenance.update(self.runtime_provenance(health))
        return result

    def _unavailable(self):
        raise ExecutionPreflightError("Managed WSL2 host-workflow execution requires W5 staging and artifact collection.")

    def resolve_executable(self, tool_id, program, engine_id=None):
        self._unavailable()

    def execute(self, workflow, record=None, store=None):
        self._unavailable()

    def cancel(self):
        self._unavailable()


def select_compute_runtime(*, info: PlatformInfo | None = None, tools: LocalToolConfiguration | None = None,
                           health_report: WSLHealthReport | None = None,
                           provisioning_health: ManagedRuntimeHealthState | None = None,
                           agent_bridge: ManagedRuntimeExecutionBridge | None = None,
                           agent_health: RuntimeBridgeHealth | None = None,
                           runtime_version: str = "", architecture: str = "x86_64") -> ComputeRuntime:
    info = info or current_platform()
    if info.operating_system is OperatingSystem.LINUX:
        return LocalLinuxRuntime(tools, info)
    return ManagedWSL2Runtime(info, health_report, provisioning_health, agent_bridge, agent_health,
                              runtime_version, architecture)


ExecutionProvider = ComputeRuntime
