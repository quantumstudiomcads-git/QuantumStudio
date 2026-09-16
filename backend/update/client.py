"""Platform-neutral signed-update selection and staging client."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Callable

from backend.release import DEFAULT_RELEASE_CHANNEL, ReleaseVersion
from backend.runtime.paths import runtime_paths
from .manifest import ReleaseManifest, parse_manifest
from .models import ArtifactRecord, EnginePackRecord, StagedArtifact, UpdateError, UpdateErrorCode, UpdateState
from .signing import UpdateVerifier
from .staging import stage_artifact
from .transport import UpdateSource


@dataclass(frozen=True)
class UpdateCheckResult:
    state: UpdateState
    current_version: str
    manifest: ReleaseManifest | None = None
    app_artifact: ArtifactRecord | None = None
    engine_pack: EnginePackRecord | None = None
    error: UpdateError | None = None

    @property
    def available(self) -> bool:
        return self.state is UpdateState.UPDATE_AVAILABLE


class UpdateClient:
    """Checks a selected channel without blocking UI or trusting filenames."""

    def __init__(self, source: UpdateSource, verifier: UpdateVerifier, *, current_version: str,
                 platform: str, architecture: str = "x86_64", channel: str = DEFAULT_RELEASE_CHANNEL,
                 runtime_schema_version: int = 1, current_engine_pack_version: str = "", paths=None):
        ReleaseVersion.validate_channel(current_version, channel if "-beta." in current_version else "stable")
        if channel not in {"beta", "stable"}:
            raise ValueError("Unsupported update channel.")
        self.source, self.verifier = source, verifier
        self.current_version, self.platform, self.architecture, self.channel = current_version, platform, architecture, channel
        self.runtime_schema_version, self.current_engine_pack_version = int(runtime_schema_version), str(current_engine_pack_version)
        self.paths = paths or runtime_paths()

    @property
    def staging_root(self) -> Path:
        return self.paths.cache / "updates"

    @property
    def state_path(self) -> Path:
        return self.paths.config / "update-state.json"

    def check(self) -> UpdateCheckResult:
        try:
            manifest = parse_manifest(self.source.fetch_manifest(self.channel), self.verifier)
            if manifest.channel != self.channel:
                raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Signed release manifest channel does not match the selected channel.")
            incoming, current = ReleaseVersion.parse(manifest.version), ReleaseVersion.parse(self.current_version)
            # A replayed older common release never becomes an Engine Pack
            # delivery vehicle.  Engine-only updates use an equal app version.
            if incoming < current:
                self._record(UpdateState.UP_TO_DATE, manifest.version)
                return UpdateCheckResult(UpdateState.UP_TO_DATE, self.current_version, manifest=manifest)
            app = manifest.platform_artifact(self.platform, self.architecture) if incoming > current else None
            engine = self._newer_compatible_engine(manifest.engine_pack)
            if app is None and engine is None:
                state = UpdateState.UP_TO_DATE
                self._record(state, manifest.version)
                return UpdateCheckResult(state, self.current_version, manifest=manifest)
            self._record(UpdateState.UPDATE_AVAILABLE, manifest.version)
            return UpdateCheckResult(UpdateState.UPDATE_AVAILABLE, self.current_version, manifest, app, engine)
        except UpdateError as error:
            self._record(UpdateState.FAILED, "", error.code.value)
            return UpdateCheckResult(UpdateState.FAILED, self.current_version, error=error)

    def stage_application(self, result: UpdateCheckResult) -> StagedArtifact:
        if not result.available or result.manifest is None or result.app_artifact is None:
            raise UpdateError(UpdateErrorCode.DOWNLOAD_FAILED, "No verified application update is available.")
        staged = stage_artifact(self.source, result.app_artifact, version=result.manifest.version,
                                staging_root=self.staging_root, verifier=self.verifier)
        self._record(UpdateState.READY_TO_INSTALL, result.manifest.version, artifact_hash=staged.sha256)
        return staged

    def stage_engine_pack(self, result: UpdateCheckResult) -> StagedArtifact:
        if not result.available or result.manifest is None or result.engine_pack is None:
            raise UpdateError(UpdateErrorCode.COMPATIBILITY_REJECTED, "No compatible Engine Pack update is available.")
        return stage_artifact(self.source, result.engine_pack, version=result.manifest.version,
                              staging_root=self.staging_root, verifier=self.verifier)

    def _newer_compatible_engine(self, engine: EnginePackRecord | None) -> EnginePackRecord | None:
        if engine is None:
            return None
        if not (engine.minimum_runtime_schema <= self.runtime_schema_version <= engine.maximum_runtime_schema):
            return None
        if engine.minimum_app_version and ReleaseVersion.parse(self.current_version) < ReleaseVersion.parse(engine.minimum_app_version):
            return None
        if engine.maximum_app_version and ReleaseVersion.parse(self.current_version) > ReleaseVersion.parse(engine.maximum_app_version):
            return None
        if self.current_engine_pack_version and self._engine_version_key(engine.version) <= self._engine_version_key(self.current_engine_pack_version):
            return None
        return engine

    @staticmethod
    def _engine_version_key(value: str) -> tuple[object, ...]:
        """Order date-like or semantic Engine Pack versions without a new dependency."""
        import re
        return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"([0-9]+)", value))

    def _record(self, state: UpdateState, version: str, result: str = "", *, artifact_hash: str = "") -> None:
        """A privacy-safe local update history; failure to record never blocks use."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            values = {"schema_version": 1, "channel": self.channel, "last_checked": datetime.now(timezone.utc).isoformat(),
                      "state": state.value, "version": version, "result": result, "artifact_hash": artifact_hash}
            temporary = self.state_path.with_name(self.state_path.name + ".tmp")
            temporary.write_text(json.dumps(values, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            os.replace(temporary, self.state_path)
        except OSError:
            pass
