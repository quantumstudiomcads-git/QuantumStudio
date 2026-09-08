"""Installed-runtime contracts shared by the application and optional engines."""

from .identity import BUILD_CHANNEL, BUILD_COMMIT, BUILD_TIMESTAMP, PRODUCT_NAME, VERSION, build_identity
from .paths import RuntimePaths, runtime_paths
from .engine_pack import EnginePackError, EnginePackManifest, EnginePackValidation, sha256_file, validate_engine_pack

__all__ = [
    "PRODUCT_NAME", "VERSION", "BUILD_CHANNEL", "BUILD_COMMIT", "BUILD_TIMESTAMP", "build_identity",
    "RuntimePaths", "runtime_paths", "EnginePackError", "EnginePackManifest",
    "EnginePackValidation", "sha256_file", "validate_engine_pack",
]

from .platform import OperatingSystem, PlatformInfo, current_platform, detect_platform
from .managed import ManagedRuntimeIdentity, RuntimeState, RuntimeType
from .wsl import DEFAULT_PROBE_TIMEOUT_SECONDS, MANAGED_DISTRO_NAME, ManagedWSLHealth, WSLCommandResult, WSLCommandRunner, WSLDistributionInfo, WSLDistributionState, WSLDiscovery, WSLHealthReport, WSLHostState, WSLProbeError, WSLRuntimeState, decode_wsl_output, parse_wsl_distributions, probe_wsl_host
__all__ += ["DEFAULT_PROBE_TIMEOUT_SECONDS", "MANAGED_DISTRO_NAME", "ManagedWSLHealth", "WSLCommandResult", "WSLCommandRunner", "WSLDistributionInfo", "WSLDistributionState", "WSLDiscovery", "WSLHealthReport", "WSLHostState", "WSLProbeError", "WSLRuntimeState", "decode_wsl_output", "parse_wsl_distributions", "probe_wsl_host"]

from .runtime_image import ManagedRuntimeImage, RuntimeImageError, RuntimeImageFormat, RuntimeImageVerification
from .provisioning import (
    DEFAULT_PROVISION_TIMEOUT_SECONDS, HOST_MARKER_FILENAME, RUNTIME_METADATA_PATH,
    ManagedRuntimeHealthState, ManagedRuntimeProvisioner, ManagedWSL2CommandInterface,
    RuntimeMetadata, RuntimeMetadataRead, RuntimeMetadataValidation, RuntimeProvisioningAction,
    RuntimeProvisioningError, RuntimeProvisioningPlan, RuntimeProvisioningResult,
    RuntimeVersionCompatibility, compare_runtime_versions, ensure_managed_runtime,
    inspect_managed_runtime, parse_runtime_version, plan_runtime_provisioning,
    read_runtime_metadata, validate_runtime_metadata,
)
__all__ += [
    "ManagedRuntimeImage", "RuntimeImageError", "RuntimeImageFormat", "RuntimeImageVerification",
    "DEFAULT_PROVISION_TIMEOUT_SECONDS", "HOST_MARKER_FILENAME", "RUNTIME_METADATA_PATH",
    "ManagedRuntimeHealthState", "ManagedRuntimeProvisioner", "ManagedWSL2CommandInterface",
    "RuntimeMetadata", "RuntimeMetadataRead", "RuntimeMetadataValidation", "RuntimeProvisioningAction",
    "RuntimeProvisioningError", "RuntimeProvisioningPlan", "RuntimeProvisioningResult",
    "RuntimeVersionCompatibility", "compare_runtime_versions", "ensure_managed_runtime",
    "inspect_managed_runtime", "parse_runtime_version", "plan_runtime_provisioning",
    "read_runtime_metadata", "validate_runtime_metadata",
]
