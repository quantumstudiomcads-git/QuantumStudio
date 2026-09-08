"""Offline, SHA-verified description of the private WSL runtime image."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re

from .engine_pack import sha256_file
from .platform import OperatingSystem
from .wsl import MANAGED_DISTRO_NAME


class RuntimeImageFormat(str, Enum):
    WSL_ROOTFS_TAR = "WSL_ROOTFS_TAR"


class RuntimeImageError(str, Enum):
    MISSING = "MISSING"
    NOT_A_FILE = "NOT_A_FILE"
    INVALID_SHA256 = "INVALID_SHA256"
    SHA256_MISMATCH = "SHA256_MISMATCH"
    PLATFORM_MISMATCH = "PLATFORM_MISMATCH"
    ARCHITECTURE_MISMATCH = "ARCHITECTURE_MISMATCH"


@dataclass(frozen=True)
class RuntimeImageVerification:
    valid: bool
    error: RuntimeImageError | None = None
    message: str = ""
    actual_sha256: str = ""


@dataclass(frozen=True)
class ManagedRuntimeImage:
    """A local WSL ``--import`` rootfs artifact, never a network resource."""

    runtime_id: str
    runtime_version: str
    platform: OperatingSystem
    architecture: str
    source_path: Path
    sha256: str
    format: RuntimeImageFormat = RuntimeImageFormat.WSL_ROOTFS_TAR
    metadata_schema_version: str = "1"
    build_id: str = ""
    build_timestamp: str = ""
    minimum_windows_release: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_path", Path(self.source_path))

    def verify(self, *, host_platform: OperatingSystem | None = None,
               host_architecture: str | None = None) -> RuntimeImageVerification:
        if self.runtime_id != MANAGED_DISTRO_NAME:
            return RuntimeImageVerification(False, RuntimeImageError.PLATFORM_MISMATCH,
                                            "Runtime image does not use the fixed managed runtime identity.")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", self.sha256):
            return RuntimeImageVerification(False, RuntimeImageError.INVALID_SHA256,
                                            "Runtime image SHA-256 must be exactly 64 hexadecimal characters.")
        if host_platform is not None and host_platform is not self.platform:
            return RuntimeImageVerification(False, RuntimeImageError.PLATFORM_MISMATCH,
                                            "Runtime image platform is incompatible with this host.")
        if host_architecture is not None and not architectures_match(self.architecture, host_architecture):
            return RuntimeImageVerification(False, RuntimeImageError.ARCHITECTURE_MISMATCH,
                                            "Runtime image architecture is incompatible with this host.")
        if not self.source_path.exists():
            return RuntimeImageVerification(False, RuntimeImageError.MISSING,
                                            "Runtime rootfs artifact does not exist.")
        if not self.source_path.is_file():
            return RuntimeImageVerification(False, RuntimeImageError.NOT_A_FILE,
                                            "Runtime rootfs artifact is not a file.")
        actual = sha256_file(self.source_path)
        if actual.casefold() != self.sha256.casefold():
            return RuntimeImageVerification(False, RuntimeImageError.SHA256_MISMATCH,
                                            "Runtime rootfs SHA-256 does not match its descriptor.", actual)
        return RuntimeImageVerification(True, actual_sha256=actual)


def architectures_match(left: str, right: str) -> bool:
    aliases = {"amd64": "x86_64", "x64": "x86_64", "x86-64": "x86_64", "aarch64": "arm64"}
    return aliases.get(str(left).lower(), str(left).lower()) == aliases.get(str(right).lower(), str(right).lower())
