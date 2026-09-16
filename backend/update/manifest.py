"""Strict parser for the authoritative, signed B6 release manifest."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import re

from backend.release import MANIFEST_SCHEMA_VERSION, ReleaseVersion
from .models import ArtifactRecord, EnginePackRecord, UpdateError, UpdateErrorCode
from .signing import UpdateVerifier

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FILENAME = re.compile(r"^[^\\/\x00]+$")


def _artifact(value: Mapping[str, Any], *, expected_platform: str = "", engine: bool = False):
    try:
        filename, url, size = str(value["filename"]), str(value["url"]), int(value["size"])
        sha256, signature, kid = str(value["sha256"]), str(value["signature"]), str(value["kid"])
        artifact_type, platform, architecture = str(value["artifact_type"]), str(value["platform"]), str(value["architecture"])
    except (KeyError, TypeError, ValueError) as error:
        raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Release artifact is incomplete.") from error
    if not _FILENAME.fullmatch(filename) or size < 0 or not _SHA256.fullmatch(sha256) or not url or not kid or (expected_platform and platform != expected_platform):
        raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Release artifact fields are invalid.")
    base = dict(filename=filename, url=url, size=size, sha256=sha256, signature=signature, kid=kid,
                artifact_type=artifact_type, platform=platform, architecture=architecture,
                minimum_app_version=str(value.get("minimum_app_version", "")), maximum_app_version=str(value.get("maximum_app_version", "")))
    if not engine:
        return ArtifactRecord(**base)
    try:
        return EnginePackRecord(**base, version=str(value["version"]), minimum_runtime_schema=int(value.get("minimum_runtime_schema", 1)), maximum_runtime_schema=int(value.get("maximum_runtime_schema", 1)))
    except (KeyError, TypeError, ValueError) as error:
        raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Engine Pack metadata is invalid.") from error


@dataclass(frozen=True)
class ReleaseManifest:
    schema_version: int
    channel: str
    version: str
    published_at: str
    minimum_supported_version: str
    mandatory: bool
    release_notes_url: str
    release_notes_summary: str
    platforms: Mapping[str, ArtifactRecord]
    engine_pack: EnginePackRecord | None
    envelope: Mapping[str, Any]

    def platform_artifact(self, platform: str, architecture: str) -> ArtifactRecord:
        value = self.platforms.get(platform)
        if value is None or value.platform != platform or value.architecture != architecture:
            raise UpdateError(UpdateErrorCode.UNSUPPORTED_PLATFORM, "No compatible application artifact is published for this platform.")
        return value


def parse_manifest(value: Mapping[str, Any], verifier: UpdateVerifier) -> ReleaseManifest:
    if not isinstance(value, Mapping):
        raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Release manifest must be a JSON object.")
    verifier.verify(value)
    try:
        schema_version, channel, version = int(value["schema_version"]), str(value["channel"]), str(value["version"])
        platforms = value["platforms"]
    except (KeyError, TypeError, ValueError) as error:
        raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Release manifest is incomplete.") from error
    if schema_version != MANIFEST_SCHEMA_VERSION:
        raise UpdateError(UpdateErrorCode.UNSUPPORTED_SCHEMA, "Unsupported release manifest schema.")
    try:
        ReleaseVersion.validate_channel(version, channel)
    except ValueError as error:
        raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, str(error)) from error
    if not isinstance(platforms, Mapping) or not platforms:
        raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Release manifest has no platform records.")
    parsed = {}
    for name, record in platforms.items():
        if not isinstance(record, Mapping):
            continue
        # Verify exactly the received signed JSON.  Reconstructing optional
        # defaults before verification would change the bytes under signature.
        verifier.verify(record)
        parsed[str(name)] = _artifact(record, expected_platform=str(name))
    if len(parsed) != len(platforms):
        raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Release platform record is malformed.")
    engine = None
    if value.get("engine_pack") is not None:
        if not isinstance(value["engine_pack"], Mapping):
            raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Engine Pack record is malformed.")
        verifier.verify(value["engine_pack"])
        engine = _artifact(value["engine_pack"], expected_platform="linux-x86_64", engine=True)
    return ReleaseManifest(schema_version, channel, version, str(value.get("published_at", "")), str(value.get("minimum_supported_version", "")),
                           bool(value.get("mandatory", False)), str(value.get("release_notes_url", "")), str(value.get("release_notes_summary", "")), parsed, engine, dict(value))
