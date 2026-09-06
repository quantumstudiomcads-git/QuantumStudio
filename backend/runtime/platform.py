"""Qt-free host platform identity used at the runtime boundary."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import platform as _platform
import struct


class OperatingSystem(str, Enum):
    LINUX = "LINUX"
    WINDOWS = "WINDOWS"
    MACOS = "MACOS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PlatformInfo:
    operating_system: OperatingSystem
    architecture: str
    python_architecture: str
    is_64_bit: bool
    machine: str
    release: str


def _os_name(system: str) -> OperatingSystem:
    normalized = str(system or "").lower()
    if normalized.startswith("linux"):
        return OperatingSystem.LINUX
    if normalized.startswith("windows") or normalized.startswith("win"):
        return OperatingSystem.WINDOWS
    if normalized in {"darwin", "mac", "macos"}:
        return OperatingSystem.MACOS
    return OperatingSystem.UNKNOWN


def detect_platform(*, system: str | None = None, machine: str | None = None,
                    release: str | None = None, python_bits: int | None = None) -> PlatformInfo:
    """Return normalized platform data; arguments make Windows behavior testable on Linux."""
    system = system if system is not None else _platform.system()
    machine = machine if machine is not None else _platform.machine()
    bits = int(python_bits or struct.calcsize("P") * 8)
    return PlatformInfo(
        operating_system=_os_name(system),
        architecture=str(machine or "unknown").lower(),
        python_architecture=f"{bits}bit",
        is_64_bit=bits == 64,
        machine=str(machine or "unknown"),
        release=str(release if release is not None else _platform.release()),
    )


def current_platform() -> PlatformInfo:
    return detect_platform()
