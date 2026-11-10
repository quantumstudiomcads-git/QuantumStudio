"""Platform-neutral signed-update selection and staging client."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import hashlib
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
                 runtime_schema_version: int = 1, current_engine_pack_version: str = "", paths=None, update_profile=None, clock=None):
        ReleaseVersion.validate_channel(current_version, channel if "-beta." in current_version else "stable")
        if channel not in {"beta", "stable"}:
            raise ValueError("Unsupported update channel.")
        self.source, self.verifier = source, verifier
        self.current_version, self.platform, self.architecture, self.channel = current_version, platform, architecture, channel
        self.runtime_schema_version, self.current_engine_pack_version = int(runtime_schema_version), str(current_engine_pack_version)
        self.paths = paths or runtime_paths()
        self.update_profile=update_profile
        self._clock=clock or (lambda:int(datetime.now(timezone.utc).timestamp()))
        if update_profile is not None:self.verifier=UpdateVerifier(update_profile.trusted_keys)
        if update_profile is not None and (not update_profile.enabled or update_profile.channel!=channel):raise ValueError('Update profile does not match client.')

    @property
    def staging_root(self) -> Path:
        root=self.paths.cache / 'updates'
        return root/self.update_profile.environment/self.update_profile.channel if self.update_profile is not None else root

    @property
    def state_path(self) -> Path:
        return self.paths.config / "update-state.json"

    def check(self) -> UpdateCheckResult:
        try:
            manifest = parse_manifest(self.source.fetch_manifest(self.channel), self.verifier,update_profile=self.update_profile,now=self._clock())
            if manifest.channel != self.channel:
                raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Signed release manifest channel does not match the selected channel.")
            incoming, current = ReleaseVersion.parse(manifest.version), ReleaseVersion.parse(self.current_version)
            # A replayed older common release never becomes an Engine Pack
            # delivery vehicle.  Engine-only updates use an equal app version.
            if incoming < current and self.update_profile is not None:raise UpdateError(UpdateErrorCode.DOWNGRADE_REJECTED,'Older application update was rejected.')
            if incoming < current:
                self._record(UpdateState.UP_TO_DATE, manifest.version)
                return UpdateCheckResult(UpdateState.UP_TO_DATE, self.current_version, manifest=manifest)
            app = manifest.platform_artifact(self.platform, self.architecture) if incoming > current else None
            engine = self._newer_compatible_engine(manifest.engine_pack)
            if self.update_profile is not None:
                from .profile import UpdateRevisionJournal
                UpdateRevisionJournal(self.paths.config/'update-revisions.sqlite3',self.update_profile).accept(manifest.envelope,self.current_version,self._clock())
            if app is None and engine is None:
                state = UpdateState.UP_TO_DATE
                self._record(state, manifest.version)
                return UpdateCheckResult(state, self.current_version, manifest=manifest)
            self._record(UpdateState.UPDATE_AVAILABLE, manifest.version)
            return UpdateCheckResult(UpdateState.UPDATE_AVAILABLE, self.current_version, manifest, app, engine)
        except UpdateError as error:
            self._record(UpdateState.FAILED, "", error.code.value)
            return UpdateCheckResult(UpdateState.FAILED, self.current_version, error=error)

    def _check_stage_profile(self,result,*,engine=False):
        if self.update_profile is None:return
        if result.manifest is None:raise UpdateError(UpdateErrorCode.MANIFEST_INVALID,'Verified update metadata is required.')
        checked=parse_manifest(result.manifest.envelope,self.verifier,update_profile=self.update_profile,now=self._clock())
        expected=checked.engine_pack if engine else checked.platform_artifact(self.platform,self.architecture)
        if (expected!=(result.engine_pack if engine else result.app_artifact) or checked.version!=result.manifest.version):
            raise UpdateError(UpdateErrorCode.MANIFEST_INVALID,'Staged artifact differs from signed metadata.')
        from .profile import UpdateRevisionJournal
        UpdateRevisionJournal(self.paths.config/'update-revisions.sqlite3',self.update_profile).accept(checked.envelope,self.current_version,self._clock())

    def _stage_root(self,result):
        if self.update_profile is None:return self.staging_root
        from .signing import canonical_json
        digest=hashlib.sha256(canonical_json(result.manifest.envelope)).hexdigest()
        return self.staging_root/str(result.manifest.envelope['revision'])/digest

    def stage_application(self, result: UpdateCheckResult) -> StagedArtifact:
        self._check_stage_profile(result)
        if not result.available or result.manifest is None or result.app_artifact is None:
            raise UpdateError(UpdateErrorCode.DOWNLOAD_FAILED, "No verified application update is available.")
        staged = stage_artifact(self.source, result.app_artifact, version=result.manifest.version,
                                staging_root=self._stage_root(result), verifier=self.verifier)
        self._check_stage_profile(result)
        self._record(UpdateState.READY_TO_INSTALL, result.manifest.version, artifact_hash=staged.sha256)
        return staged

    def stage_engine_pack(self, result: UpdateCheckResult) -> StagedArtifact:
        self._check_stage_profile(result,engine=True)
        if not result.available or result.manifest is None or result.engine_pack is None:
            raise UpdateError(UpdateErrorCode.COMPATIBILITY_REJECTED, "No compatible Engine Pack update is available.")
        staged=stage_artifact(self.source, result.engine_pack, version=result.manifest.version,
                              staging_root=self._stage_root(result), verifier=self.verifier)
        self._check_stage_profile(result,engine=True)
        return staged

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
