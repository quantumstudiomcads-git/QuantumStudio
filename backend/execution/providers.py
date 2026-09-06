"""Compute-runtime boundary; scientific code remains provider-independent."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.runtime.managed import ManagedRuntimeIdentity, RuntimeState, RuntimeType
from backend.runtime.platform import OperatingSystem, PlatformInfo, current_platform
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
    """Structural WSL2 placeholder. It must never probe, install, or invoke WSL in W1."""
    def __init__(self, info: PlatformInfo | None = None):
        self.info = info or current_platform()
        self.identity = ManagedRuntimeIdentity.managed_wsl2(self.info)

    def probe(self) -> RuntimeProbe:
        return RuntimeProbe(RuntimeState.AVAILABLE_NOT_READY, "Managed WSL2 runtime is reserved for W2; no WSL probe is performed.")

    def _unavailable(self):
        raise ExecutionPreflightError("Managed WSL2 scientific runtime is not implemented in W1.")

    def resolve_executable(self, tool_id, program, engine_id=None):
        self._unavailable()

    def execute(self, workflow, record=None, store=None):
        self._unavailable()

    def cancel(self):
        self._unavailable()


def select_compute_runtime(*, info: PlatformInfo | None = None, tools: LocalToolConfiguration | None = None) -> ComputeRuntime:
    info = info or current_platform()
    if info.operating_system is OperatingSystem.LINUX:
        return LocalLinuxRuntime(tools, info)
    if info.operating_system is OperatingSystem.WINDOWS:
        return ManagedWSL2Runtime(info)
    return ManagedWSL2Runtime(info)


ExecutionProvider = ComputeRuntime
