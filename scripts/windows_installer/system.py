"""Installer-only documented Windows prerequisite command construction."""
from __future__ import annotations
from dataclasses import dataclass
import platform, subprocess, sys
from backend.runtime.platform import OperatingSystem, current_platform
from backend.runtime.wsl import WSLCommandRunner, WSLDiscovery
from .contracts import HostAssessment, HostPrerequisite

FEATURES=("Microsoft-Windows-Subsystem-Linux","VirtualMachinePlatform")

def is_windows_11(*, release: str, build: int) -> bool:
    """Windows 11 identifies as NT 10; its build number is authoritative."""
    return str(release).startswith("11") or int(build) >= 22000

def prerequisite_argv(feature: str)->tuple[str,...]:
    if feature not in FEATURES: raise ValueError("Unsupported Windows prerequisite feature.")
    return ("dism.exe","/online","/enable-feature",f"/featurename:{feature}","/all","/norestart")

@dataclass
class WindowsPrerequisiteController:
    """Privileged installer helper; no normal GUI imports this module."""
    runner: object=subprocess
    def assess(self)->HostAssessment:
        info=current_platform()
        if info.operating_system is not OperatingSystem.WINDOWS: return HostAssessment(False,info.architecture,detail="Windows 11 x86_64 is required.")
        version=platform.version().split(".")
        build=int(version[-1]) if version and version[-1].isdigit() else 0
        architecture={"amd64":"x86_64","x64":"x86_64"}.get(info.architecture.lower(),info.architecture.lower())
        if architecture!="x86_64" or not is_windows_11(release=info.release,build=build): return HostAssessment(False,architecture,0,detail="Windows 11 x86_64 is required.")
        health=WSLDiscovery(WSLCommandRunner(),info).probe()
        if health.wsl2_available: return HostAssessment(True,"x86_64",11,HostPrerequisite.READY,"WSL2 is already available.")
        return HostAssessment(True,"x86_64",11,HostPrerequisite.NEEDS_ENABLEMENT,"Windows compute components need preparation.")
    def enable(self)->HostPrerequisite:
        if not sys.platform.startswith("win"): return HostPrerequisite.FAILED
        reboot=False
        for feature in FEATURES:
            completed=self.runner.run(list(prerequisite_argv(feature)),shell=False,check=False,capture_output=True)
            if completed.returncode not in {0,3010}: return HostPrerequisite.FAILED
            reboot = reboot or completed.returncode==3010
        return HostPrerequisite.REBOOT_REQUIRED if reboot else HostPrerequisite.READY
