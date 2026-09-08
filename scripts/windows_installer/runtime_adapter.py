"""Installer-only adapters over the existing W3/W5 trusted runtime APIs.

These adapters deliberately have no distro parameter.  They translate typed
W3/W5 results into installer component outcomes; policy for destructive
recreation remains outside this module and requires explicit confirmation.
"""
from __future__ import annotations

from backend.runtime.managed_science import EnginePackDescriptor, ManagedEnginePackDeployment
from backend.runtime.provisioning import (
    ManagedRuntimeProvisioner, RuntimeProvisioningAction, RuntimeProvisioningError,
)
from .contracts import ComponentAction, ComponentResult, InstallerPayload


class ManagedRuntimeInstallerAdapter:
    """Narrow W3/W5 adapter for an elevated installer helper, never the GUI."""

    def __init__(self, provisioner_factory=ManagedRuntimeProvisioner, engine_deployment=None):
        self.provisioner_factory = provisioner_factory
        self.engine_deployment = engine_deployment

    @staticmethod
    def _component(result) -> ComponentResult:
        if result.success:
            action = ComponentAction.NO_ACTION if result.performed_action in {
                RuntimeProvisioningAction.NO_ACTION, RuntimeProvisioningAction.VERIFY_RUNTIME
            } else ComponentAction.INSTALL
            return ComponentResult(action, "; ".join(result.diagnostics))
        if result.error in {
            RuntimeProvisioningError.UNKNOWN_INSTALLATION_DIRECTORY,
            RuntimeProvisioningError.DESTRUCTIVE_ACTION_NOT_AUTHORIZED,
        }:
            return ComponentResult(ComponentAction.OWNERSHIP_CONFLICT, "; ".join(result.diagnostics))
        return ComponentResult(ComponentAction.FAILED, "; ".join(result.diagnostics))

    def ensure_runtime(self, payload: InstallerPayload) -> ComponentResult:
        if payload.runtime_image is None:
            return ComponentResult(ComponentAction.FAILED, "Runtime image is missing.")
        # W3 verifies the image and refuses recreation without authorization.
        result = self.provisioner_factory(payload.runtime_image).ensure_managed_runtime(allow_destructive=False)
        return self._component(result)

    def install_engine_pack(self, payload: InstallerPayload) -> ComponentResult:
        if payload.engine_pack_root is None or self.engine_deployment is None:
            return ComponentResult(ComponentAction.FAILED, "Verified Engine Pack deployment is unavailable.")
        descriptor = EnginePackDescriptor(
            pack_id="scientific", source_root=payload.engine_pack_root,
            expected_manifest_sha256=payload.engine_pack_manifest_sha256,
        )
        try:
            response = self.engine_deployment.install(descriptor)
        except Exception as error:
            return ComponentResult(ComponentAction.FAILED, "Verified Engine Pack installation failed: " + str(error))
        return ComponentResult(ComponentAction.INSTALL, "Verified Engine Pack activated.", str(response.get("version", "")))
