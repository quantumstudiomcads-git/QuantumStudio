"""Versioned, standard-library-only control protocol for qs-runtime-agent."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import posixpath
import re
from typing import Any, Mapping

PROTOCOL_SCHEMA_VERSION = 1
# Schema 1 remains extensible: W5 adds named capabilities without changing W4 run requests.
AGENT_VERSION = "2"
POSIX_PROCESS_ID_MIN = 1
POSIX_PROCESS_ID_MAX = 2_147_483_647
WINDOWS_PROCESS_ID_MIN = 1
WINDOWS_PROCESS_ID_MAX = 4_294_967_295


def is_valid_posix_process_identity(value: object) -> bool:
    """Return whether value is a serialized positive signed-32-bit POSIX PID/PGID."""
    return (type(value) is int
            and POSIX_PROCESS_ID_MIN <= value <= POSIX_PROCESS_ID_MAX)


def is_valid_windows_process_identity(value: object) -> bool:
    """Return whether value is a genuine positive Windows DWORD process ID."""
    return (type(value) is int
            and WINDOWS_PROCESS_ID_MIN <= value <= WINDOWS_PROCESS_ID_MAX)


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AgentStatus(str, Enum):
    READY = "READY"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    EXECUTABLE_REJECTED = "EXECUTABLE_REJECTED"
    CWD_REJECTED = "CWD_REJECTED"
    STDIN_MISSING = "STDIN_MISSING"
    PROCESS_START_FAILED = "PROCESS_START_FAILED"
    PROCESS_EXITED = "PROCESS_EXITED"
    PROCESS_TIMEOUT = "PROCESS_TIMEOUT"
    INTERNAL_AGENT_ERROR = "INTERNAL_AGENT_ERROR"
    TRANSFER_REJECTED = "TRANSFER_REJECTED"
    TRANSFER_FAILED = "TRANSFER_FAILED"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_RUNNING = "TASK_RUNNING"
    TASK_FINISHED = "TASK_FINISHED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_CANCELLATION_INDETERMINATE = "TASK_CANCELLATION_INDETERMINATE"
    TASK_OUTCOME_INDETERMINATE = "TASK_OUTCOME_INDETERMINATE"
    TASK_CONTROL_PERSISTENCE_FAILED = "TASK_CONTROL_PERSISTENCE_FAILED"


@dataclass(frozen=True)
class RuntimePath:
    """Absolute POSIX path in the runtime namespace, never a host path."""
    value: str

    def __post_init__(self) -> None:
        value = str(self.value)
        if "\x00" in value or "\\" in value or not value.startswith("/") or re.match(r"^[A-Za-z]:", value):
            raise ProtocolError("INVALID_RUNTIME_PATH", "Runtime paths must be absolute POSIX paths without NUL bytes or backslashes.")
        normalized = posixpath.normpath(value)
        if not normalized.startswith("/"):
            raise ProtocolError("INVALID_RUNTIME_PATH", "Runtime path normalization escaped the POSIX root.")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


def _string(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value) or "\x00" in str(value):
        raise ProtocolError("INVALID_REQUEST", f"{name} must be a {'non-empty ' if not allow_empty else ''}string without NUL bytes.")
    return value


def _environment(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ProtocolError("INVALID_REQUEST", "environment must be a string-to-string object.")
    clean: dict[str, str] = {}
    for key, item in value.items():
        key = _string(key, "environment key")
        item = _string(item, "environment value", allow_empty=True)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ProtocolError("INVALID_REQUEST", "environment key is invalid.")
        clean[key] = item
    return clean


@dataclass(frozen=True)
class RuntimeProcessRequest:
    task_id: str
    executable: RuntimePath
    argv: tuple[str, ...]
    cwd: RuntimePath
    environment: dict[str, str]
    stdin_path: RuntimePath | None = None
    stdout_path: RuntimePath | None = None
    stderr_path: RuntimePath | None = None
    timeout_seconds: float | None = None
    schema_version: int = PROTOCOL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _string(self.task_id, "task_id")
        if self.schema_version != PROTOCOL_SCHEMA_VERSION:
            raise ProtocolError("UNSUPPORTED_SCHEMA", "Runtime-agent protocol schema is unsupported.")
        if not isinstance(self.executable, RuntimePath) or not isinstance(self.cwd, RuntimePath):
            raise ProtocolError("INVALID_REQUEST", "executable and cwd must be runtime paths.")
        argv = tuple(_string(value, "argv item", allow_empty=True) for value in self.argv)
        object.__setattr__(self, "argv", argv)
        object.__setattr__(self, "environment", _environment(self.environment))
        for name in ("stdin_path", "stdout_path", "stderr_path"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, RuntimePath):
                raise ProtocolError("INVALID_REQUEST", f"{name} must be a runtime path or null.")
        if self.timeout_seconds is not None and (not isinstance(self.timeout_seconds, (int, float)) or self.timeout_seconds <= 0):
            raise ProtocolError("INVALID_REQUEST", "timeout_seconds must be a positive number or null.")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeProcessRequest":
        if not isinstance(payload, Mapping):
            raise ProtocolError("INVALID_REQUEST", "Runtime task payload must be an object.")
        schema = payload.get("schema_version")
        if schema != PROTOCOL_SCHEMA_VERSION:
            raise ProtocolError("UNSUPPORTED_SCHEMA", "Runtime-agent protocol schema is unsupported.")
        argv = payload.get("argv", [])
        if not isinstance(argv, list):
            raise ProtocolError("INVALID_REQUEST", "argv must be a JSON array.")
        def path(name: str, optional: bool = False):
            value = payload.get(name)
            if value is None and optional:
                return None
            return RuntimePath(_string(value, name))
        return cls(_string(payload.get("task_id"), "task_id"), path("executable"), tuple(argv), path("cwd"),
                   _environment(payload.get("environment", {})), path("stdin_path", True), path("stdout_path", True),
                   path("stderr_path", True), payload.get("timeout_seconds"), int(schema))

    @classmethod
    def from_json(cls, payload: bytes | str) -> "RuntimeProcessRequest":
        try:
            return cls.from_dict(json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload))
        except json.JSONDecodeError as error:
            raise ProtocolError("INVALID_REQUEST", f"Runtime task JSON is malformed: {error.msg}") from error

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "task_id": self.task_id, "executable": str(self.executable),
                "argv": list(self.argv), "cwd": str(self.cwd), "environment": dict(self.environment),
                "stdin_path": str(self.stdin_path) if self.stdin_path else None,
                "stdout_path": str(self.stdout_path) if self.stdout_path else None,
                "stderr_path": str(self.stderr_path) if self.stderr_path else None,
                "timeout_seconds": self.timeout_seconds}

    def to_json(self) -> bytes:
        return (json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


@dataclass(frozen=True)
class RuntimeProcessResult:
    task_id: str
    status: AgentStatus
    started: bool
    finished: bool
    return_code: int | None = None
    runtime_pid: int | None = None
    runtime_process_group: int | None = None
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float | None = None
    diagnostic: str = ""
    schema_version: int = PROTOCOL_SCHEMA_VERSION
    agent_version: str = AGENT_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeProcessResult":
        if not isinstance(payload, Mapping) or payload.get("schema_version") != PROTOCOL_SCHEMA_VERSION:
            raise ProtocolError("AGENT_PROTOCOL_ERROR", "Runtime-agent response schema is unsupported or malformed.")
        try:
            status = AgentStatus(payload["status"])
            return cls(_string(payload["task_id"], "task_id"), status, bool(payload["started"]), bool(payload["finished"]),
                       payload.get("return_code"), payload.get("runtime_pid"), payload.get("runtime_process_group"),
                       str(payload.get("started_at", "")), str(payload.get("finished_at", "")), payload.get("duration_seconds"),
                       str(payload.get("diagnostic", "")), int(payload["schema_version"]), str(payload.get("agent_version", "")))
        except (KeyError, TypeError, ValueError) as error:
            raise ProtocolError("AGENT_PROTOCOL_ERROR", "Runtime-agent response is malformed.") from error

    @classmethod
    def from_json(cls, payload: bytes | str) -> "RuntimeProcessResult":
        try:
            return cls.from_dict(json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload))
        except json.JSONDecodeError as error:
            raise ProtocolError("AGENT_PROTOCOL_ERROR", "Runtime-agent response is not JSON.") from error

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "agent_version": self.agent_version, "task_id": self.task_id,
                "status": self.status.value, "started": self.started, "finished": self.finished,
                "return_code": self.return_code, "runtime_pid": self.runtime_pid,
                "runtime_process_group": self.runtime_process_group, "started_at": self.started_at,
                "finished_at": self.finished_at, "duration_seconds": self.duration_seconds, "diagnostic": self.diagnostic}

    def to_json(self) -> bytes:
        return (json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


@dataclass(frozen=True)
class RuntimeAgentHealth:
    ready: bool
    agent_version: str
    schema_version: int
    diagnostic: str = ""
    capabilities: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, payload: bytes | str) -> "RuntimeAgentHealth":
        try:
            data = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
            if not isinstance(data, Mapping) or data.get("schema_version") != PROTOCOL_SCHEMA_VERSION or data.get("status") != "READY":
                raise ValueError
            capabilities = data.get("capabilities", [])
            if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
                raise ValueError
            return cls(True, _string(data.get("agent_version"), "agent_version"), int(data["schema_version"]),
                       str(data.get("diagnostic", "")), tuple(capabilities))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise ProtocolError("AGENT_PROTOCOL_ERROR", "Runtime-agent health response is malformed or incompatible.") from error

    def to_json(self) -> bytes:
        return (json.dumps({"schema_version": self.schema_version, "agent_version": self.agent_version,
                            "status": "READY", "diagnostic": self.diagnostic,
                            "capabilities": list(self.capabilities)}, sort_keys=True) + "\n").encode("utf-8")


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
