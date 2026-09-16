"""Typed data and failures for the release-update protocol."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class UpdateState(str, Enum):
    IDLE = "IDLE"
    CHECKING = "CHECKING"
    UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
    DOWNLOADING = "DOWNLOADING"
    VERIFYING = "VERIFYING"
    READY_TO_INSTALL = "READY_TO_INSTALL"
    INSTALLING = "INSTALLING"
    RESTART_REQUIRED = "RESTART_REQUIRED"
    UP_TO_DATE = "UP_TO_DATE"
    FAILED = "FAILED"


class UpdateErrorCode(str, Enum):
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    MANIFEST_INVALID = "MANIFEST_INVALID"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    DISK_SPACE = "DISK_SPACE"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INSTALLER_LAUNCH_FAILED = "INSTALLER_LAUNCH_FAILED"
    RUNTIME_UPDATE_FAILED = "RUNTIME_UPDATE_FAILED"
    DOWNGRADE_REJECTED = "DOWNGRADE_REJECTED"
    COMPATIBILITY_REJECTED = "COMPATIBILITY_REJECTED"


class UpdateError(RuntimeError):
    def __init__(self, code: UpdateErrorCode, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ArtifactRecord:
    filename: str
    url: str
    size: int
    sha256: str
    signature: str
    kid: str
    artifact_type: str
    platform: str
    architecture: str
    minimum_app_version: str = ""
    maximum_app_version: str = ""


@dataclass(frozen=True)
class EnginePackRecord(ArtifactRecord):
    version: str = ""
    minimum_runtime_schema: int = 1
    maximum_runtime_schema: int = 1


@dataclass(frozen=True)
class StagedArtifact:
    record: ArtifactRecord
    path: Path
    sha256: str
    size: int
