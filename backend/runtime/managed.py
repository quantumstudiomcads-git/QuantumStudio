"""Identity and health contracts for application-managed scientific runtimes."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .platform import OperatingSystem, PlatformInfo, current_platform


class RuntimeType(str, Enum):
    LOCAL_LINUX = "LOCAL_LINUX"
    MANAGED_WSL2 = "MANAGED_WSL2"


class RuntimeState(str, Enum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    AVAILABLE_NOT_READY = "AVAILABLE_NOT_READY"
    READY = "READY"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class ManagedRuntimeIdentity:
    runtime_id: str
    runtime_type: RuntimeType
    runtime_version: str = ""
    platform: OperatingSystem = OperatingSystem.UNKNOWN
    architecture: str = "unknown"
    installation_state: RuntimeState = RuntimeState.NOT_AVAILABLE

    @classmethod
    def local_linux(cls, info: PlatformInfo | None = None) -> "ManagedRuntimeIdentity":
        info = info or current_platform()
        return cls("local-linux", RuntimeType.LOCAL_LINUX, info.release, info.operating_system, info.architecture, RuntimeState.READY)

    @classmethod
    def managed_wsl2(cls, info: PlatformInfo | None = None) -> "ManagedRuntimeIdentity":
        info = info or current_platform()
        return cls("managed-wsl2", RuntimeType.MANAGED_WSL2, "", info.operating_system, info.architecture, RuntimeState.AVAILABLE_NOT_READY)
