"""Read-only WSL host and managed-runtime discovery.

This module deliberately stops at host-level WSL enumeration.  It never starts
a distribution and never performs installation or mutation operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Protocol, Sequence

from .platform import OperatingSystem, PlatformInfo, current_platform


MANAGED_DISTRO_NAME = "QuantumStudioRuntime"
DEFAULT_PROBE_TIMEOUT_SECONDS = 3.0


class WSLProbeError(str, Enum):
    EXECUTABLE_NOT_FOUND = "EXECUTABLE_NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    COMMAND_FAILED = "COMMAND_FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"


class WSLHostState(str, Enum):
    NON_WINDOWS = "NON_WINDOWS"
    COMMAND_MISSING = "COMMAND_MISSING"
    UNAVAILABLE = "UNAVAILABLE"
    AVAILABLE = "AVAILABLE"
    WSL2_AVAILABLE = "WSL2_AVAILABLE"
    PROBE_TIMEOUT = "PROBE_TIMEOUT"
    PROBE_ERROR = "PROBE_ERROR"


class WSLRuntimeState(str, Enum):
    RUNTIME_NOT_INSTALLED = "RUNTIME_NOT_INSTALLED"
    REGISTERED_WSL1 = "REGISTERED_WSL1"
    REGISTERED_WSL2 = "REGISTERED_WSL2"
    RUNTIME_DEGRADED = "RUNTIME_DEGRADED"
    PROBE_TIMEOUT = "PROBE_TIMEOUT"
    PROBE_ERROR = "PROBE_ERROR"


class WSLDistributionState(str, Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    INSTALLING = "INSTALLING"
    UNINSTALLING = "UNINSTALLING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class WSLDistributionInfo:
    name: str
    state: WSLDistributionState
    wsl_version: int | None
    is_default: bool = False
    raw_state: str = ""


@dataclass(frozen=True)
class WSLCommandResult:
    argv: tuple[str, ...]
    returncode: int | None = None
    stdout: bytes = b""
    stderr: bytes = b""
    error: WSLProbeError | None = None
    error_message: str = ""


@dataclass(frozen=True)
class ManagedWSLHealth:
    name: str
    registered: bool
    wsl_version: int | None
    distro_state: WSLDistributionState | None
    health_state: WSLRuntimeState


@dataclass(frozen=True)
class WSLHealthReport:
    platform: OperatingSystem
    architecture: str
    host_state: WSLHostState
    command_available: bool
    wsl_probe_successful: bool
    wsl2_available: bool
    distributions: tuple[WSLDistributionInfo, ...]
    managed_runtime: ManagedWSLHealth
    probe_errors: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        """Return diagnostics-safe JSON-compatible data."""
        return {
            "platform": self.platform.value,
            "architecture": self.architecture,
            "host_state": self.host_state.value,
            "command_available": self.command_available,
            "wsl_probe_successful": self.wsl_probe_successful,
            "wsl2_available": self.wsl2_available,
            "registered_distributions": [
                {
                    "name": item.name,
                    "state": item.state.value,
                    "wsl_version": item.wsl_version,
                    "is_default": item.is_default,
                    "raw_state": item.raw_state,
                }
                for item in self.distributions
            ],
            "managed_runtime": {
                "name": self.managed_runtime.name,
                "registered": self.managed_runtime.registered,
                "wsl_version": self.managed_runtime.wsl_version,
                "distro_state": self.managed_runtime.distro_state.value if self.managed_runtime.distro_state else None,
                "health_state": self.managed_runtime.health_state.value,
            },
            "probe_errors": list(self.probe_errors),
        }


class WSLCommandRunnerProtocol(Protocol):
    def available(self) -> bool: ...
    def run(self, arguments: Sequence[str]) -> WSLCommandResult: ...


class WSLCommandRunner:
    """Small injectable runner for read-only ``wsl.exe`` information commands."""

    def __init__(self, executable: str = "wsl.exe", timeout: float = DEFAULT_PROBE_TIMEOUT_SECONDS):
        self.executable = executable
        self.timeout = timeout

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def run(self, arguments: Sequence[str]) -> WSLCommandResult:
        return self._run(arguments)

    def run_with_input(self, arguments: Sequence[str], input_data: bytes, *, timeout: float | None = None) -> WSLCommandResult:
        """Run a controlled WSL command with a binary stdin control payload.

        W4 uses this only for the fixed managed-runtime agent.  The caller
        still supplies structured argv; this method never creates a shell.
        ``None`` deliberately means no artificial task-lifetime timeout.
        """
        return self._run(arguments, input_data=input_data, timeout=timeout)

    def run_with_streaming_input(self, arguments: Sequence[str], prefix: bytes, source_path: str | Path, *, timeout: float | None = None) -> WSLCommandResult:
        """Send a bounded JSON header plus a file stream to the fixed agent.

        Bulk artifacts are never base64 encoded or accumulated in memory.
        """
        argv = (self.executable, *tuple(arguments))
        try:
            with Path(source_path).open("rb") as source:
                process = subprocess.Popen(list(argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
                assert process.stdin is not None
                process.stdin.write(prefix)
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    process.stdin.write(block)
                process.stdin.close()
                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                except ValueError:  # communicate() after explicit close on some Python versions
                    process.wait(timeout=timeout); stdout = process.stdout.read() if process.stdout else b""; stderr = process.stderr.read() if process.stderr else b""
        except FileNotFoundError as exc:
            return WSLCommandResult(argv, error=WSLProbeError.EXECUTABLE_NOT_FOUND, error_message=str(exc))
        except subprocess.TimeoutExpired as exc:
            process.kill(); stdout, stderr = process.communicate()
            return WSLCommandResult(argv, stdout=_as_bytes(stdout), stderr=_as_bytes(stderr), error=WSLProbeError.TIMEOUT, error_message=str(exc))
        except OSError as exc:
            return WSLCommandResult(argv, error=WSLProbeError.COMMAND_FAILED, error_message=str(exc))
        return WSLCommandResult(argv, process.returncode, _as_bytes(stdout), _as_bytes(stderr))

    def run_with_streaming_output(self, arguments: Sequence[str], input_data: bytes, destination_path: str | Path, *, timeout: float | None = None) -> WSLCommandResult:
        """Stream raw agent output directly to a caller-owned temporary file."""
        argv = (self.executable, *tuple(arguments))
        try:
            with Path(destination_path).open("wb") as destination:
                completed = subprocess.run(list(argv), input=input_data, stdout=destination, stderr=subprocess.PIPE,
                                           timeout=timeout, check=False, shell=False)
        except FileNotFoundError as exc:
            return WSLCommandResult(argv, error=WSLProbeError.EXECUTABLE_NOT_FOUND, error_message=str(exc))
        except subprocess.TimeoutExpired as exc:
            return WSLCommandResult(argv, stderr=_as_bytes(exc.stderr), error=WSLProbeError.TIMEOUT, error_message=str(exc))
        except OSError as exc:
            return WSLCommandResult(argv, error=WSLProbeError.COMMAND_FAILED, error_message=str(exc))
        return WSLCommandResult(argv, completed.returncode, b"", _as_bytes(completed.stderr))

    def _run(self, arguments: Sequence[str], *, input_data: bytes | None = None,
             timeout: float | None = None) -> WSLCommandResult:
        argv = (self.executable, *tuple(arguments))
        try:
            completed = subprocess.run(
                list(argv), shell=False, capture_output=True, input=input_data,
                timeout=self.timeout if timeout is None and input_data is None else timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            return WSLCommandResult(argv, error=WSLProbeError.EXECUTABLE_NOT_FOUND, error_message=str(exc))
        except subprocess.TimeoutExpired as exc:
            return WSLCommandResult(argv, stdout=_as_bytes(exc.stdout), stderr=_as_bytes(exc.stderr), error=WSLProbeError.TIMEOUT, error_message=str(exc))
        except OSError as exc:
            return WSLCommandResult(argv, error=WSLProbeError.COMMAND_FAILED, error_message=str(exc))
        return WSLCommandResult(argv, completed.returncode, _as_bytes(completed.stdout), _as_bytes(completed.stderr))


def _as_bytes(value) -> bytes:
    if value is None:
        return b""
    return value if isinstance(value, bytes) else str(value).encode("utf-8", errors="replace")


def decode_wsl_output(value: bytes | str) -> str:
    """Decode common Windows subprocess encodings without exposing decode errors."""
    if isinstance(value, str):
        return value
    for encoding in ("utf-8-sig", "utf-16", os.device_encoding(1), "mbcs"):
        if not encoding:
            continue
        try:
            return value.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return value.decode("utf-8", errors="replace")


_DISTRO_LINE = re.compile(
    r"^\s*(?P<default>\*)?\s*(?P<name>.*?)\s+(?P<state>Running|Stopped|Installing|Uninstalling|Unknown)\s+(?P<version>[12])\s*$",
    re.IGNORECASE,
)


def parse_wsl_distributions(output: bytes | str) -> tuple[tuple[WSLDistributionInfo, ...], tuple[str, ...]]:
    """Parse the stable table shape while retaining controlled malformed-line diagnostics."""
    records: list[WSLDistributionInfo] = []
    errors: list[str] = []
    lines = decode_wsl_output(output).replace("\r\n", "\n").split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped or ("NAME" in stripped.upper() and "STATE" in stripped.upper()):
            continue
        match = _DISTRO_LINE.match(line)
        if not match:
            errors.append(f"unparsed distro line: {stripped[:120]}")
            continue
        state_text = match.group("state").upper()
        state = WSLDistributionState.__members__.get(state_text, WSLDistributionState.UNKNOWN)
        records.append(WSLDistributionInfo(
            name=match.group("name").strip(), state=state,
            wsl_version=int(match.group("version")),
            is_default=bool(match.group("default")), raw_state=match.group("state"),
        ))
    return tuple(records), tuple(errors)


class WSLDiscovery:
    """Probe only host-level WSL information; never executes a distro command."""

    def __init__(self, runner: WSLCommandRunnerProtocol | None = None, info: PlatformInfo | None = None):
        self.info = info or current_platform()
        self.runner = runner or WSLCommandRunner()

    def probe(self) -> WSLHealthReport:
        if self.info.operating_system is not OperatingSystem.WINDOWS:
            return _report(self.info, WSLHostState.NON_WINDOWS, False, False, (), (WSLProbeError.UNSUPPORTED_PLATFORM.value,))
        if not self.runner.available():
            return _report(self.info, WSLHostState.COMMAND_MISSING, False, False, (), (WSLProbeError.EXECUTABLE_NOT_FOUND.value,))

        list_result = self.runner.run(("--list", "--verbose"))
        if list_result.error is WSLProbeError.TIMEOUT:
            return _report(self.info, WSLHostState.PROBE_TIMEOUT, True, False, (), (WSLProbeError.TIMEOUT.value,))
        if list_result.error is not None:
            return _report(self.info, WSLHostState.PROBE_ERROR, True, False, (), (list_result.error.value,))
        if list_result.returncode != 0:
            return _report(self.info, WSLHostState.UNAVAILABLE, True, False, (), (WSLProbeError.COMMAND_FAILED.value,))

        distributions, parse_errors = parse_wsl_distributions(list_result.stdout)
        errors = list(parse_errors)
        if parse_errors and not distributions:
            return _report(self.info, WSLHostState.PROBE_ERROR, True, False, (), (WSLProbeError.MALFORMED_OUTPUT.value, *errors))

        # --version is enrichment only. A failure here must not erase a valid distro table.
        version_result = self.runner.run(("--version",))
        version_ok = version_result.error is None and version_result.returncode == 0
        if version_result.error is not None:
            errors.append(version_result.error.value)
        elif version_result.returncode != 0:
            errors.append(WSLProbeError.COMMAND_FAILED.value)
        wsl2 = version_ok or any(item.wsl_version == 2 for item in distributions)
        host_state = WSLHostState.WSL2_AVAILABLE if wsl2 else WSLHostState.AVAILABLE
        managed = _managed_health(distributions)
        return WSLHealthReport(self.info.operating_system, self.info.architecture, host_state, True, True, wsl2, distributions, managed, tuple(errors))


def _managed_health(distributions: tuple[WSLDistributionInfo, ...]) -> ManagedWSLHealth:
    match = next((item for item in distributions if item.name.casefold() == MANAGED_DISTRO_NAME.casefold()), None)
    if match is None:
        return ManagedWSLHealth(MANAGED_DISTRO_NAME, False, None, None, WSLRuntimeState.RUNTIME_NOT_INSTALLED)
    if match.wsl_version == 1:
        return ManagedWSLHealth(match.name, True, 1, match.state, WSLRuntimeState.REGISTERED_WSL1)
    if match.wsl_version == 2:
        return ManagedWSLHealth(match.name, True, 2, match.state, WSLRuntimeState.REGISTERED_WSL2)
    return ManagedWSLHealth(match.name, True, match.wsl_version, match.state, WSLRuntimeState.RUNTIME_DEGRADED)


def _report(info, host_state, command_available, probe_successful, distributions, errors):
    return WSLHealthReport(
        info.operating_system, info.architecture, host_state, command_available,
        probe_successful, any(item.wsl_version == 2 for item in distributions),
        tuple(distributions), _managed_health(tuple(distributions)), tuple(errors),
    )


def probe_wsl_host(*, info: PlatformInfo | None = None, runner: WSLCommandRunnerProtocol | None = None) -> WSLHealthReport:
    return WSLDiscovery(runner=runner, info=info).probe()
