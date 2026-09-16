"""Safe platform handoff after generic staging has completed verification."""
from __future__ import annotations

from pathlib import Path
import subprocess

from .models import StagedArtifact, UpdateError, UpdateErrorCode


class WindowsInstallerHandoff:
    """Launch an already verified Inno installer; application shutdown is caller-owned."""

    arguments = ("/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS")

    def launch(self, staged: StagedArtifact) -> None:
        if staged.record.platform != "windows-x86_64" or staged.record.artifact_type != "windows-installer" or staged.path.suffix.lower() != ".exe":
            raise UpdateError(UpdateErrorCode.UNSUPPORTED_PLATFORM, "Verified artifact is not a Windows installer.")
        try:
            subprocess.Popen([str(staged.path), *self.arguments], shell=False)
        except OSError as error:
            raise UpdateError(UpdateErrorCode.INSTALLER_LAUNCH_FAILED, "Verified Windows installer could not be launched.") from error


class LinuxAppImageHandoff:
    """Return the verified AppImage for explicit replacement/launch handling.

    Replacing an arbitrary running AppImage is unsafe.  The GUI therefore
    presents this verified staged path until a managed launcher target is
    configured; it never overwrites an executing binary.
    """

    def ready_path(self, staged: StagedArtifact) -> Path:
        if staged.record.platform != "linux-x86_64" or staged.record.artifact_type != "appimage":
            raise UpdateError(UpdateErrorCode.UNSUPPORTED_PLATFORM, "Verified artifact is not a Linux AppImage.")
        return staged.path
