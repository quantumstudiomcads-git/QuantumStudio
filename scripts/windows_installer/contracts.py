"""Qt-free installer payload, host, and component contracts."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import hashlib, json
from backend.runtime.runtime_image import ManagedRuntimeImage
from backend.runtime.wsl import MANAGED_DISTRO_NAME
from backend.runtime.engine_pack import validate_engine_pack

class HostPrerequisite(str,Enum): READY="READY"; NEEDS_ENABLEMENT="NEEDS_ENABLEMENT"; REBOOT_REQUIRED="REBOOT_REQUIRED"; UNSUPPORTED="UNSUPPORTED"; FAILED="FAILED"
class ComponentAction(str,Enum): NO_ACTION="NO_ACTION"; INSTALL="INSTALL"; REPAIR="REPAIR"; UPGRADE="UPGRADE"; OWNERSHIP_CONFLICT="OWNERSHIP_CONFLICT"; FAILED="FAILED"
class InstallerProfile(str,Enum): GUI_ONLY="GUI_ONLY"; GUI_PLUS_RUNTIME="GUI_PLUS_RUNTIME"; FULL_SCIENTIFIC="FULL_SCIENTIFIC"

class InstallerContractError(RuntimeError):pass

def sha256_file(path: str|Path)->str:
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""): digest.update(block)
    return digest.hexdigest()

@dataclass(frozen=True)
class InstallerPayload:
    app_bundle: Path; app_manifest: Path; app_manifest_sha256: str; runtime_image: ManagedRuntimeImage|None=None; engine_pack_root: Path|None=None; engine_pack_manifest_sha256: str=""; notices: tuple[Path,...]=()
    def validate(self, profile: InstallerProfile) -> None:
        if not self.app_bundle.is_dir() or not self.app_manifest.is_file(): raise InstallerContractError("Verified W6 application bundle or build manifest is missing.")
        if sha256_file(self.app_manifest)!=self.app_manifest_sha256: raise InstallerContractError("Application build manifest SHA-256 mismatch.")
        try: manifest=json.loads(self.app_manifest.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError) as error: raise InstallerContractError("Application build manifest is invalid.") from error
        if manifest.get("platform")!="windows" or manifest.get("architecture")!="x86_64": raise InstallerContractError("Application payload platform/architecture is incompatible.")
        if profile is not InstallerProfile.GUI_ONLY:
            if self.runtime_image is None: raise InstallerContractError("Runtime image payload is required by this installer profile.")
            verification=self.runtime_image.verify()
            if not verification.valid: raise InstallerContractError("Runtime image SHA-256 verification failed.")
        if profile is InstallerProfile.FULL_SCIENTIFIC and (self.engine_pack_root is None or not self.engine_pack_manifest_sha256): raise InstallerContractError("Engine Pack payload is required by FULL_SCIENTIFIC profile.")
        if profile is InstallerProfile.FULL_SCIENTIFIC:
            assert self.engine_pack_root is not None
            manifest=self.engine_pack_root / "engine-pack.json"
            if not manifest.is_file() or sha256_file(manifest) != self.engine_pack_manifest_sha256: raise InstallerContractError("Engine Pack manifest SHA-256 mismatch.")
            verification=validate_engine_pack(self.engine_pack_root,platform_name="linux",architecture="x86_64")
            if not verification.valid: raise InstallerContractError("Engine Pack payload validation failed.")

@dataclass(frozen=True)
class HostAssessment:
    supported: bool; architecture: str; windows_major: int=0; prerequisite: HostPrerequisite=HostPrerequisite.READY; detail: str=""
    def require_supported(self):
        if not self.supported or self.architecture!="x86_64" or self.windows_major<11: raise InstallerContractError(self.detail or "Windows 11 x86_64 is required.")

@dataclass(frozen=True)
class ComponentResult:
    action: ComponentAction; detail: str=""; version: str=""
    @property
    def okay(self)->bool:return self.action in {ComponentAction.NO_ACTION,ComponentAction.INSTALL,ComponentAction.REPAIR,ComponentAction.UPGRADE}

# The only installer-owned distro identity; no caller can supply another name.
MANAGED_RUNTIME_ID=MANAGED_DISTRO_NAME
