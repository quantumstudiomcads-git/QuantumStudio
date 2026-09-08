"""Deterministic provisioning for the one private WSL2 runtime.

This module manages exactly ``QuantumStudioRuntime``.  It is intentionally not
an arbitrary distro-management or command-execution API, and it never starts a
scientific executable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Callable

from .paths import RuntimePaths, runtime_paths
from .platform import OperatingSystem, PlatformInfo, current_platform
from .runtime_image import ManagedRuntimeImage, RuntimeImageVerification, architectures_match
from .wsl import (
    MANAGED_DISTRO_NAME, WSLCommandResult, WSLCommandRunner,
    WSLCommandRunnerProtocol, WSLDiscovery, WSLHealthReport, WSLHostState,
    WSLProbeError, WSLRuntimeState,
)

RUNTIME_METADATA_PATH = "/opt/quantumstudio/runtime/runtime.json"
HOST_MARKER_FILENAME = "quantumstudio-runtime-host.json"
HOST_MARKER_SCHEMA_VERSION = "1"
SUPPORTED_RUNTIME_METADATA_SCHEMA = "1"
DEFAULT_PROVISION_TIMEOUT_SECONDS = 120.0


class ManagedRuntimeHealthState(str, Enum):
    ABSENT = "ABSENT"
    REGISTERED_WSL1 = "REGISTERED_WSL1"
    REGISTERED_WSL2_UNVERIFIED = "REGISTERED_WSL2_UNVERIFIED"
    METADATA_VALID = "METADATA_VALID"
    METADATA_INVALID = "METADATA_INVALID"
    VERSION_INCOMPATIBLE = "VERSION_INCOMPATIBLE"
    IMAGE_INTEGRITY_FAILED = "IMAGE_INTEGRITY_FAILED"
    HOST_PREREQUISITE_MISSING = "HOST_PREREQUISITE_MISSING"


class RuntimeProvisioningAction(str, Enum):
    NO_ACTION = "NO_ACTION"
    IMPORT_RUNTIME = "IMPORT_RUNTIME"
    VERIFY_RUNTIME = "VERIFY_RUNTIME"
    REPAIR_METADATA = "REPAIR_METADATA"
    RECREATE_RUNTIME = "RECREATE_RUNTIME"
    HOST_PREREQUISITE_REQUIRED = "HOST_PREREQUISITE_REQUIRED"
    BLOCKED = "BLOCKED"


class RuntimeProvisioningError(str, Enum):
    IMAGE_INTEGRITY_FAILED = "IMAGE_INTEGRITY_FAILED"
    HOST_PREREQUISITE_MISSING = "HOST_PREREQUISITE_MISSING"
    UNKNOWN_INSTALLATION_DIRECTORY = "UNKNOWN_INSTALLATION_DIRECTORY"
    DESTRUCTIVE_ACTION_NOT_AUTHORIZED = "DESTRUCTIVE_ACTION_NOT_AUTHORIZED"
    IMPORT_TIMEOUT = "IMPORT_TIMEOUT"
    IMPORT_FAILED = "IMPORT_FAILED"
    PARTIAL_IMPORT = "PARTIAL_IMPORT"
    POST_IMPORT_DISCOVERY_FAILED = "POST_IMPORT_DISCOVERY_FAILED"
    POST_IMPORT_WSL1 = "POST_IMPORT_WSL1"
    POST_IMPORT_ABSENT = "POST_IMPORT_ABSENT"
    METADATA_READ_FAILED = "METADATA_READ_FAILED"
    METADATA_INVALID = "METADATA_INVALID"
    VERSION_INCOMPATIBLE = "VERSION_INCOMPATIBLE"
    HOST_METADATA_WRITE_FAILED = "HOST_METADATA_WRITE_FAILED"
    UNREGISTER_FAILED = "UNREGISTER_FAILED"


class RuntimeVersionCompatibility(str, Enum):
    CURRENT = "CURRENT"
    OLDER_COMPATIBLE = "OLDER_COMPATIBLE"
    OLDER_REQUIRES_UPGRADE = "OLDER_REQUIRES_UPGRADE"
    NEWER_COMPATIBLE = "NEWER_COMPATIBLE"
    NEWER_UNSUPPORTED = "NEWER_UNSUPPORTED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class RuntimeMetadata:
    runtime_id: str
    runtime_version: str
    schema_version: str
    architecture: str
    build_id: str
    build_timestamp: str
    image_sha256: str


@dataclass(frozen=True)
class RuntimeMetadataValidation:
    metadata: RuntimeMetadata | None
    valid: bool
    message: str = ""
    image_matches_desired: bool = False


@dataclass(frozen=True)
class RuntimeMetadataRead:
    validation: RuntimeMetadataValidation
    command: WSLCommandResult | None = None
    error: RuntimeProvisioningError | None = None


@dataclass(frozen=True)
class RuntimeInspection:
    discovery: WSLHealthReport
    metadata: RuntimeMetadataValidation | None
    health: ManagedRuntimeHealthState
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeProvisioningPlan:
    action: RuntimeProvisioningAction
    desired_runtime_id: str
    desired_runtime_version: str
    installation_root: Path
    reason: str
    diagnostics: tuple[str, ...] = ()
    destructive: bool = False
    version_compatibility: RuntimeVersionCompatibility | None = None
    image_verification: RuntimeImageVerification | None = None


@dataclass(frozen=True)
class RuntimeProvisioningResult:
    requested_action: RuntimeProvisioningAction
    performed_action: RuntimeProvisioningAction | None
    success: bool
    changed_system_state: bool
    destructive: bool
    before_health: ManagedRuntimeHealthState
    after_health: ManagedRuntimeHealthState
    diagnostics: tuple[str, ...] = ()
    error: RuntimeProvisioningError | None = None
    command: WSLCommandResult | None = None


class ManagedWSL2CommandInterface:
    """The only W3 mutating/inside-distro command surface.

    Each method fixes the distribution identity internally.  Callers cannot
    inject user distro names, Linux command text, or a metadata path.
    """

    def __init__(self, runner: WSLCommandRunnerProtocol | None = None):
        self.runner = runner or WSLCommandRunner(timeout=DEFAULT_PROVISION_TIMEOUT_SECONDS)

    def import_managed_runtime(self, installation_root: Path, rootfs: Path) -> WSLCommandResult:
        return self.runner.run(("--import", MANAGED_DISTRO_NAME, str(installation_root), str(rootfs), "--version", "2"))

    def unregister_managed_runtime(self) -> WSLCommandResult:
        return self.runner.run(("--unregister", MANAGED_DISTRO_NAME))

    def read_managed_runtime_metadata(self) -> WSLCommandResult:
        return self.runner.run(("--distribution", MANAGED_DISTRO_NAME, "--exec", "cat", RUNTIME_METADATA_PATH))


def parse_runtime_version(value: str) -> tuple[int, int, int] | None:
    """Parse the deliberately independent ``major.minor-runtime.revision`` form."""
    match = re.fullmatch(r"(\d+)\.(\d+)-runtime\.(\d+)", str(value).strip())
    return tuple(map(int, match.groups())) if match else None


def compare_runtime_versions(installed: str, desired: str) -> RuntimeVersionCompatibility:
    left, right = parse_runtime_version(installed), parse_runtime_version(desired)
    if left is None or right is None:
        return RuntimeVersionCompatibility.INVALID
    if left == right:
        return RuntimeVersionCompatibility.CURRENT
    if left[:2] == right[:2]:
        return RuntimeVersionCompatibility.OLDER_COMPATIBLE if left[2] < right[2] else RuntimeVersionCompatibility.NEWER_COMPATIBLE
    return RuntimeVersionCompatibility.OLDER_REQUIRES_UPGRADE if left[:2] < right[:2] else RuntimeVersionCompatibility.NEWER_UNSUPPORTED


def validate_runtime_metadata(payload: str | bytes | dict, desired_image: ManagedRuntimeImage) -> RuntimeMetadataValidation:
    try:
        data = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload) if not isinstance(payload, dict) else payload
        if not isinstance(data, dict):
            raise ValueError("runtime metadata must be a JSON object")
        metadata = RuntimeMetadata(
            runtime_id=str(data["runtime_id"]), runtime_version=str(data["runtime_version"]),
            schema_version=str(data["schema_version"]), architecture=str(data["architecture"]),
            build_id=str(data.get("build_id", "")), build_timestamp=str(data.get("build_timestamp", "")),
            image_sha256=str(data["image_sha256"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return RuntimeMetadataValidation(None, False, f"Malformed runtime metadata: {exc}")
    if metadata.runtime_id != MANAGED_DISTRO_NAME:
        return RuntimeMetadataValidation(metadata, False, "Runtime metadata identity does not match QuantumStudioRuntime.")
    if metadata.schema_version != SUPPORTED_RUNTIME_METADATA_SCHEMA:
        return RuntimeMetadataValidation(metadata, False, "Runtime metadata schema is unsupported.")
    if parse_runtime_version(metadata.runtime_version) is None:
        return RuntimeMetadataValidation(metadata, False, "Runtime metadata version is not parseable.")
    if not architectures_match(metadata.architecture, desired_image.architecture):
        return RuntimeMetadataValidation(metadata, False, "Runtime metadata architecture is incompatible.")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", metadata.image_sha256):
        return RuntimeMetadataValidation(metadata, False, "Runtime metadata image SHA-256 is invalid.")
    image_matches = metadata.image_sha256.casefold() == desired_image.sha256.casefold()
    # A different version naturally has a different image.  Hash disagreement
    # is therefore fatal only when metadata claims the desired version.
    if metadata.runtime_version == desired_image.runtime_version and not image_matches:
        return RuntimeMetadataValidation(metadata, False, "Runtime metadata image SHA-256 disagrees with the desired image.", False)
    return RuntimeMetadataValidation(metadata, True, image_matches_desired=image_matches)


def read_runtime_metadata(commands: ManagedWSL2CommandInterface, desired_image: ManagedRuntimeImage) -> RuntimeMetadataRead:
    result = commands.read_managed_runtime_metadata()
    if result.error is not None or result.returncode != 0:
        return RuntimeMetadataRead(RuntimeMetadataValidation(None, False, "Could not read runtime metadata."), result,
                                   RuntimeProvisioningError.METADATA_READ_FAILED)
    validation = validate_runtime_metadata(result.stdout, desired_image)
    return RuntimeMetadataRead(validation, result,
                               None if validation.valid else RuntimeProvisioningError.METADATA_INVALID)


def inspect_managed_runtime(discovery: WSLHealthReport, commands: ManagedWSL2CommandInterface,
                            desired_image: ManagedRuntimeImage) -> RuntimeInspection:
    managed = discovery.managed_runtime
    if discovery.host_state in {WSLHostState.NON_WINDOWS, WSLHostState.COMMAND_MISSING, WSLHostState.UNAVAILABLE,
                                WSLHostState.PROBE_TIMEOUT, WSLHostState.PROBE_ERROR}:
        return RuntimeInspection(discovery, None, ManagedRuntimeHealthState.HOST_PREREQUISITE_MISSING, discovery.probe_errors)
    if not managed.registered:
        return RuntimeInspection(discovery, None, ManagedRuntimeHealthState.ABSENT)
    if managed.health_state is WSLRuntimeState.REGISTERED_WSL1:
        return RuntimeInspection(discovery, None, ManagedRuntimeHealthState.REGISTERED_WSL1)
    if managed.health_state is not WSLRuntimeState.REGISTERED_WSL2:
        return RuntimeInspection(discovery, None, ManagedRuntimeHealthState.REGISTERED_WSL2_UNVERIFIED,
                                 ("Managed distro registration is degraded.",))
    read = read_runtime_metadata(commands, desired_image)
    if not read.validation.valid:
        return RuntimeInspection(discovery, read.validation, ManagedRuntimeHealthState.METADATA_INVALID,
                                 (read.validation.message,))
    relation = compare_runtime_versions(read.validation.metadata.runtime_version, desired_image.runtime_version)
    if relation in {RuntimeVersionCompatibility.NEWER_UNSUPPORTED, RuntimeVersionCompatibility.INVALID}:
        return RuntimeInspection(discovery, read.validation, ManagedRuntimeHealthState.VERSION_INCOMPATIBLE,
                                 (f"Runtime version compatibility is {relation.value}.",))
    return RuntimeInspection(discovery, read.validation, ManagedRuntimeHealthState.METADATA_VALID)


def _host_marker_path(installation_root: Path) -> Path:
    return installation_root / HOST_MARKER_FILENAME


def _read_host_marker(installation_root: Path) -> dict | None:
    path = _host_marker_path(installation_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _owned_installation_root(installation_root: Path) -> bool:
    marker = _read_host_marker(installation_root)
    return bool(marker and marker.get("schema_version") == HOST_MARKER_SCHEMA_VERSION and marker.get("runtime_id") == MANAGED_DISTRO_NAME)


def _directory_is_unknown(installation_root: Path) -> bool:
    if not installation_root.exists():
        return False
    try:
        return any(installation_root.iterdir()) and not _owned_installation_root(installation_root)
    except OSError:
        return True


def plan_runtime_provisioning(discovery: WSLHealthReport, desired_image: ManagedRuntimeImage,
                               desired_version: str | None = None, *, installation_root: Path,
                               metadata: RuntimeMetadataValidation | None = None,
                               info: PlatformInfo | None = None) -> RuntimeProvisioningPlan:
    """Build a mutation-free, explainable plan before provisioning anything."""
    info = info or current_platform()
    desired_version = desired_version or desired_image.runtime_version
    verification = desired_image.verify(host_platform=info.operating_system, host_architecture=info.architecture)
    common = dict(desired_runtime_id=MANAGED_DISTRO_NAME, desired_runtime_version=desired_version,
                  installation_root=Path(installation_root), image_verification=verification)
    if info.operating_system is not OperatingSystem.WINDOWS or not discovery.wsl2_available:
        return RuntimeProvisioningPlan(RuntimeProvisioningAction.HOST_PREREQUISITE_REQUIRED,
                                       reason="WSL2 host prerequisites are unavailable; W3 does not install Windows features.",
                                       diagnostics=discovery.probe_errors, **common)
    if not verification.valid:
        return RuntimeProvisioningPlan(RuntimeProvisioningAction.BLOCKED,
                                       reason=f"Runtime image integrity verification failed: {verification.message}",
                                       diagnostics=(verification.error.value,) if verification.error else (), **common)
    managed = discovery.managed_runtime
    if not managed.registered:
        if _directory_is_unknown(Path(installation_root)):
            return RuntimeProvisioningPlan(RuntimeProvisioningAction.BLOCKED,
                                           reason="Managed installation directory contains unrecognized content.",
                                           diagnostics=(RuntimeProvisioningError.UNKNOWN_INSTALLATION_DIRECTORY.value,), **common)
        return RuntimeProvisioningPlan(RuntimeProvisioningAction.IMPORT_RUNTIME,
                                       reason="Managed distro QuantumStudioRuntime is not registered.", **common)
    if managed.health_state is WSLRuntimeState.REGISTERED_WSL1:
        if _directory_is_unknown(Path(installation_root)):
            return RuntimeProvisioningPlan(RuntimeProvisioningAction.BLOCKED,
                                           reason="Managed installation directory is not owned by Quantum Studio.",
                                           diagnostics=(RuntimeProvisioningError.UNKNOWN_INSTALLATION_DIRECTORY.value,), **common)
        return RuntimeProvisioningPlan(RuntimeProvisioningAction.RECREATE_RUNTIME,
                                       reason="Managed runtime is registered as WSL1; Quantum Studio requires WSL2.", destructive=True, **common)
    if managed.health_state is not WSLRuntimeState.REGISTERED_WSL2:
        return RuntimeProvisioningPlan(RuntimeProvisioningAction.BLOCKED,
                                       reason="Managed runtime registration is degraded and cannot be safely repaired.", **common)
    if metadata is None or not metadata.valid or metadata.metadata is None:
        if _directory_is_unknown(Path(installation_root)):
            return RuntimeProvisioningPlan(RuntimeProvisioningAction.BLOCKED,
                                           reason="Runtime metadata is invalid and the installation directory is unrecognized.",
                                           diagnostics=(RuntimeProvisioningError.UNKNOWN_INSTALLATION_DIRECTORY.value,), **common)
        return RuntimeProvisioningPlan(RuntimeProvisioningAction.RECREATE_RUNTIME,
                                       reason="Managed WSL2 runtime metadata is missing or invalid and requires explicit recreation.",
                                       destructive=True, **common)
    relation = compare_runtime_versions(metadata.metadata.runtime_version, desired_version)
    if relation is RuntimeVersionCompatibility.NEWER_UNSUPPORTED:
        return RuntimeProvisioningPlan(RuntimeProvisioningAction.BLOCKED,
                                       reason="Installed managed runtime is newer and unsupported; it will not be downgraded.",
                                       version_compatibility=relation,
                                       diagnostics=(RuntimeProvisioningError.VERSION_INCOMPATIBLE.value,), **common)
    if relation in {RuntimeVersionCompatibility.INVALID, RuntimeVersionCompatibility.OLDER_REQUIRES_UPGRADE}:
        return RuntimeProvisioningPlan(RuntimeProvisioningAction.RECREATE_RUNTIME,
                                       reason=f"Managed runtime version requires an explicit replacement ({relation.value}).",
                                       destructive=True, version_compatibility=relation, **common)
    marker = _read_host_marker(Path(installation_root))
    marker_matches = bool(marker and marker.get("runtime_id") == MANAGED_DISTRO_NAME and
                          marker.get("runtime_version") == metadata.metadata.runtime_version and
                          marker.get("image_sha256", "").casefold() == metadata.metadata.image_sha256.casefold())
    if not marker_matches:
        return RuntimeProvisioningPlan(RuntimeProvisioningAction.REPAIR_METADATA,
                                       reason="Runtime metadata is valid but host ownership metadata must be repaired.",
                                       version_compatibility=relation, **common)
    action = RuntimeProvisioningAction.NO_ACTION if relation is RuntimeVersionCompatibility.CURRENT else RuntimeProvisioningAction.VERIFY_RUNTIME
    return RuntimeProvisioningPlan(action, reason="Managed runtime is already metadata-verified and compatible.",
                                   version_compatibility=relation, **common)


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass  # Windows does not consistently permit opening a directory.
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _host_marker(image: ManagedRuntimeImage, installation_root: Path, metadata: RuntimeMetadata) -> dict:
    return {
        "schema_version": HOST_MARKER_SCHEMA_VERSION,
        "runtime_id": MANAGED_DISTRO_NAME,
        "runtime_version": metadata.runtime_version,
        "architecture": metadata.architecture,
        "image_sha256": metadata.image_sha256,
        "installation_root": str(installation_root),
        "source_image_sha256": image.sha256,
    }


class ManagedRuntimeProvisioner:
    """Plan first, then perform only explicit operations on the fixed distro."""

    def __init__(self, desired_image: ManagedRuntimeImage, *, info: PlatformInfo | None = None,
                 runner: WSLCommandRunnerProtocol | None = None, paths: RuntimePaths | None = None,
                 discovery_factory: Callable[..., WSLDiscovery] = WSLDiscovery):
        self.desired_image = desired_image
        self.info = info or current_platform()
        self.runner = runner or WSLCommandRunner(timeout=DEFAULT_PROVISION_TIMEOUT_SECONDS)
        self.commands = ManagedWSL2CommandInterface(self.runner)
        self.paths = paths or runtime_paths()
        self.installation_root = self.paths.managed_wsl_runtime / MANAGED_DISTRO_NAME
        self.discovery_factory = discovery_factory

    def discover(self) -> WSLHealthReport:
        return self.discovery_factory(runner=self.runner, info=self.info).probe()

    def inspect(self, discovery: WSLHealthReport | None = None) -> RuntimeInspection:
        return inspect_managed_runtime(discovery or self.discover(), self.commands, self.desired_image)

    def plan(self, inspection: RuntimeInspection | None = None) -> RuntimeProvisioningPlan:
        inspection = inspection or self.inspect()
        return plan_runtime_provisioning(inspection.discovery, self.desired_image, installation_root=self.installation_root,
                                         metadata=inspection.metadata, info=self.info)

    def ensure_managed_runtime(self, *, allow_destructive: bool = False) -> RuntimeProvisioningResult:
        before = self.inspect()
        plan = self.plan(before)
        return self.execute(plan, before=before, allow_destructive=allow_destructive)

    def execute(self, plan: RuntimeProvisioningPlan, *, before: RuntimeInspection | None = None,
                allow_destructive: bool = False) -> RuntimeProvisioningResult:
        before = before or self.inspect()
        if plan.action in {RuntimeProvisioningAction.NO_ACTION, RuntimeProvisioningAction.VERIFY_RUNTIME}:
            return self._result(plan, True, False, before.health, before.health)
        if plan.action is RuntimeProvisioningAction.HOST_PREREQUISITE_REQUIRED:
            return self._result(plan, False, False, before.health, before.health, RuntimeProvisioningError.HOST_PREREQUISITE_MISSING)
        if plan.action is RuntimeProvisioningAction.BLOCKED:
            error = RuntimeProvisioningError.IMAGE_INTEGRITY_FAILED if plan.image_verification and not plan.image_verification.valid else RuntimeProvisioningError.UNKNOWN_INSTALLATION_DIRECTORY
            return self._result(plan, False, False, before.health, before.health, error)
        if plan.destructive and not allow_destructive:
            return self._result(plan, False, False, before.health, before.health, RuntimeProvisioningError.DESTRUCTIVE_ACTION_NOT_AUTHORIZED)
        if plan.action is RuntimeProvisioningAction.REPAIR_METADATA:
            metadata = before.metadata.metadata if before.metadata else None
            try:
                if metadata is None:
                    raise OSError("No valid runtime metadata is available for host marker repair.")
                _atomic_write_json(_host_marker_path(self.installation_root), _host_marker(self.desired_image, self.installation_root, metadata))
            except OSError as exc:
                return self._result(plan, False, False, before.health, before.health,
                                    RuntimeProvisioningError.HOST_METADATA_WRITE_FAILED, (str(exc),))
            return self._result(plan, True, True, before.health, ManagedRuntimeHealthState.METADATA_VALID)
        if plan.action is RuntimeProvisioningAction.RECREATE_RUNTIME:
            unregistered = self.commands.unregister_managed_runtime()
            if unregistered.error is not None or unregistered.returncode != 0:
                return self._result(plan, False, False, before.health, before.health,
                                    RuntimeProvisioningError.UNREGISTER_FAILED, command=unregistered)
            # Deletion is permitted only after explicit authorization and only
            # for a root carrying our durable ownership marker.
            if self.installation_root.exists() and _owned_installation_root(self.installation_root):
                shutil.rmtree(self.installation_root)
            elif self.installation_root.exists() and any(self.installation_root.iterdir()):
                return self._result(plan, False, True, before.health, ManagedRuntimeHealthState.ABSENT,
                                    RuntimeProvisioningError.UNKNOWN_INSTALLATION_DIRECTORY, command=unregistered)
            return self._import(plan, before.health, destructive=True)
        if plan.action is RuntimeProvisioningAction.IMPORT_RUNTIME:
            return self._import(plan, before.health)
        return self._result(plan, False, False, before.health, before.health, RuntimeProvisioningError.IMPORT_FAILED)

    def _import(self, plan: RuntimeProvisioningPlan, before_health: ManagedRuntimeHealthState, *, destructive: bool = False) -> RuntimeProvisioningResult:
        try:
            if _directory_is_unknown(self.installation_root):
                return self._result(plan, False, False, before_health, before_health, RuntimeProvisioningError.UNKNOWN_INSTALLATION_DIRECTORY)
            self.installation_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return self._result(plan, False, False, before_health, before_health, RuntimeProvisioningError.HOST_METADATA_WRITE_FAILED, (str(exc),))
        command = self.commands.import_managed_runtime(self.installation_root, self.desired_image.source_path)
        after = self.inspect()
        if command.error is WSLProbeError.TIMEOUT:
            return self._result(plan, False, after.health is not before_health, before_health, after.health,
                                RuntimeProvisioningError.IMPORT_TIMEOUT, command=command, destructive=destructive)
        if command.error is not None or command.returncode != 0:
            error = RuntimeProvisioningError.PARTIAL_IMPORT if after.discovery.managed_runtime.registered else RuntimeProvisioningError.IMPORT_FAILED
            return self._result(plan, False, after.discovery.managed_runtime.registered, before_health, after.health,
                                error, command=command, destructive=destructive)
        if after.discovery.host_state in {WSLHostState.NON_WINDOWS, WSLHostState.COMMAND_MISSING,
                                          WSLHostState.UNAVAILABLE, WSLHostState.PROBE_TIMEOUT,
                                          WSLHostState.PROBE_ERROR}:
            return self._result(plan, False, True, before_health, after.health,
                                RuntimeProvisioningError.POST_IMPORT_DISCOVERY_FAILED, command=command,
                                destructive=destructive)
        if not after.discovery.managed_runtime.registered:
            return self._result(plan, False, True, before_health, after.health,
                                RuntimeProvisioningError.POST_IMPORT_ABSENT, command=command, destructive=destructive)
        if after.discovery.managed_runtime.wsl_version != 2:
            return self._result(plan, False, True, before_health, after.health,
                                RuntimeProvisioningError.POST_IMPORT_WSL1, command=command, destructive=destructive)
        if after.health is not ManagedRuntimeHealthState.METADATA_VALID or not after.metadata or not after.metadata.metadata:
            return self._result(plan, False, True, before_health, after.health,
                                RuntimeProvisioningError.METADATA_INVALID, command=command, destructive=destructive)
        if (after.metadata.metadata.runtime_version != self.desired_image.runtime_version or
                not after.metadata.image_matches_desired):
            return self._result(plan, False, True, before_health, ManagedRuntimeHealthState.METADATA_INVALID,
                                RuntimeProvisioningError.METADATA_INVALID,
                                ("Imported runtime metadata does not match the requested image version or digest."),
                                command, destructive)
        try:
            _atomic_write_json(_host_marker_path(self.installation_root), _host_marker(self.desired_image, self.installation_root, after.metadata.metadata))
        except OSError as exc:
            return self._result(plan, False, True, before_health, after.health,
                                RuntimeProvisioningError.HOST_METADATA_WRITE_FAILED, (str(exc),), command, destructive)
        return self._result(plan, True, True, before_health, after.health, command=command, destructive=destructive)

    @staticmethod
    def _result(plan: RuntimeProvisioningPlan, success: bool, changed: bool,
                before: ManagedRuntimeHealthState, after: ManagedRuntimeHealthState,
                error: RuntimeProvisioningError | None = None, diagnostics: tuple[str, ...] = (),
                command: WSLCommandResult | None = None, destructive: bool | None = None) -> RuntimeProvisioningResult:
        return RuntimeProvisioningResult(plan.action, plan.action if success or command else None, success, changed,
                                         plan.destructive if destructive is None else destructive, before, after,
                                         (plan.reason, *plan.diagnostics, *diagnostics), error, command)


def ensure_managed_runtime(image: ManagedRuntimeImage, *, info: PlatformInfo | None = None,
                           runner: WSLCommandRunnerProtocol | None = None, paths: RuntimePaths | None = None,
                           allow_destructive: bool = False) -> RuntimeProvisioningResult:
    """Convenience boundary for installer code; no action occurs on import."""
    return ManagedRuntimeProvisioner(image, info=info, runner=runner, paths=paths).ensure_managed_runtime(
        allow_destructive=allow_destructive)
