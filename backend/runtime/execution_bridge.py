"""Host-side, fixed-identity transport for qs-runtime-agent.

This is a control channel only.  It has no workflow staging, host-path
translation, Engine Pack discovery, artifact collection, or engine-specific
logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence

from runtime_agent.protocol import (
    AGENT_VERSION, PROTOCOL_SCHEMA_VERSION, ProtocolError, RuntimeAgentHealth,
    RuntimeProcessRequest, RuntimeProcessResult,
)

from .wsl import MANAGED_DISTRO_NAME, WSLCommandResult, WSLProbeError

RUNTIME_AGENT_PATH = "/opt/quantumstudio/runtime/bin/qs-runtime-agent"
DEFAULT_AGENT_CONTROL_TIMEOUT_SECONDS = 10.0
SUPPORTED_AGENT_VERSIONS = frozenset({"1", AGENT_VERSION})


class RuntimeBridgeError(str, Enum):
    RUNTIME_NOT_READY = "RUNTIME_NOT_READY"
    WSL_TRANSPORT_FAILED = "WSL_TRANSPORT_FAILED"
    WSL_TRANSPORT_TIMEOUT = "WSL_TRANSPORT_TIMEOUT"
    AGENT_UNAVAILABLE = "AGENT_UNAVAILABLE"
    AGENT_PROTOCOL_ERROR = "AGENT_PROTOCOL_ERROR"
    AGENT_REJECTED_TASK = "AGENT_REJECTED_TASK"
    PROCESS_COMPLETED = "PROCESS_COMPLETED"


@dataclass(frozen=True)
class RuntimeBridgeHealth:
    ready: bool
    agent_version: str = ""
    schema_version: int | None = None
    diagnostic: str = ""
    error: RuntimeBridgeError | None = None
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeBridgeResult:
    request: RuntimeProcessRequest
    process: RuntimeProcessResult | None
    error: RuntimeBridgeError
    diagnostic: str = ""
    command: WSLCommandResult | None = None

    @property
    def completed(self) -> bool:
        return self.error is RuntimeBridgeError.PROCESS_COMPLETED and self.process is not None


class RuntimeAgentCommandRunnerProtocol(Protocol):
    def available(self) -> bool: ...
    def run_with_input(self, arguments: Sequence[str], input_data: bytes, *, timeout: float | None = None) -> WSLCommandResult: ...
    def run_with_streaming_input(self, arguments: Sequence[str], prefix: bytes, source_path: str, *, timeout: float | None = None) -> WSLCommandResult: ...
    def run_with_streaming_output(self, arguments: Sequence[str], input_data: bytes, destination_path: str, *, timeout: float | None = None) -> WSLCommandResult: ...


def agent_argv(command: str) -> tuple[str, ...]:
    """Return the sole permitted WSL agent endpoint; distro identity is fixed."""
    if command not in {"health", "version", "run", "stage-in", "stage-out", "status", "cancel", "install-engine-pack"}:
        raise ValueError("Unsupported managed runtime-agent command.")
    return ("--distribution", MANAGED_DISTRO_NAME, "--exec", RUNTIME_AGENT_PATH, command)


class ManagedRuntimeExecutionBridge:
    """Synchronous JSON-over-stdin transport to the exact managed distro."""

    def __init__(self, runner: RuntimeAgentCommandRunnerProtocol, *, control_timeout: float = DEFAULT_AGENT_CONTROL_TIMEOUT_SECONDS):
        self.runner = runner
        self.control_timeout = float(control_timeout)

    def probe_agent(self) -> RuntimeBridgeHealth:
        if not self.runner.available():
            return RuntimeBridgeHealth(False, diagnostic="wsl.exe is unavailable.", error=RuntimeBridgeError.RUNTIME_NOT_READY)
        result = self.runner.run_with_input(agent_argv("health"), b"", timeout=self.control_timeout)
        if result.error is WSLProbeError.TIMEOUT:
            return RuntimeBridgeHealth(False, diagnostic="Runtime-agent health probe timed out.", error=RuntimeBridgeError.WSL_TRANSPORT_TIMEOUT)
        if result.error is not None or result.returncode != 0:
            return RuntimeBridgeHealth(False, diagnostic=result.error_message or "Runtime-agent health probe failed.", error=RuntimeBridgeError.AGENT_UNAVAILABLE)
        try:
            health = RuntimeAgentHealth.from_json(result.stdout)
        except ProtocolError as error:
            return RuntimeBridgeHealth(False, diagnostic=str(error), error=RuntimeBridgeError.AGENT_PROTOCOL_ERROR)
        if health.schema_version != PROTOCOL_SCHEMA_VERSION or health.agent_version not in SUPPORTED_AGENT_VERSIONS:
            return RuntimeBridgeHealth(False, health.agent_version, health.schema_version,
                                       "Runtime-agent protocol schema or version is incompatible.", RuntimeBridgeError.AGENT_UNAVAILABLE)
        return RuntimeBridgeHealth(True, health.agent_version, health.schema_version, health.diagnostic, None, health.capabilities)

    def execute(self, request: RuntimeProcessRequest) -> RuntimeBridgeResult:
        if not self.runner.available():
            return RuntimeBridgeResult(request, None, RuntimeBridgeError.RUNTIME_NOT_READY, "wsl.exe is unavailable.")
        # No host-side task timeout is imposed: the agent owns an explicit
        # request timeout and W5 will provide cancellation/control.
        result = self.runner.run_with_input(agent_argv("run"), request.to_json(), timeout=None)
        if result.error is WSLProbeError.TIMEOUT:
            return RuntimeBridgeResult(request, None, RuntimeBridgeError.WSL_TRANSPORT_TIMEOUT,
                                       "Managed runtime transport timed out.", result)
        if result.error is not None or result.returncode != 0:
            return RuntimeBridgeResult(request, None, RuntimeBridgeError.WSL_TRANSPORT_FAILED,
                                       result.error_message or "Managed runtime transport failed.", result)
        try:
            process = RuntimeProcessResult.from_json(result.stdout)
        except ProtocolError as error:
            return RuntimeBridgeResult(request, None, RuntimeBridgeError.AGENT_PROTOCOL_ERROR, str(error), result)
        if process.task_id != request.task_id:
            return RuntimeBridgeResult(request, None, RuntimeBridgeError.AGENT_PROTOCOL_ERROR,
                                       "Runtime-agent response task identity does not match the request.", result)
        error = RuntimeBridgeError.PROCESS_COMPLETED if process.status.value == "PROCESS_EXITED" else RuntimeBridgeError.AGENT_REJECTED_TASK
        return RuntimeBridgeResult(request, process, error, process.diagnostic, result)

    @staticmethod
    def provenance(*, runtime_version: str, architecture: str, agent_version: str = AGENT_VERSION) -> dict[str, str | int]:
        return {"provider_type": "MANAGED_WSL2", "runtime_id": MANAGED_DISTRO_NAME,
                "runtime_version": runtime_version, "runtime_platform": "linux", "architecture": architecture,
                "agent_version": agent_version, "agent_protocol_schema": PROTOCOL_SCHEMA_VERSION}
