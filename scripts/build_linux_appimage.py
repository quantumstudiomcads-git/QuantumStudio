"""Build an official Linux/x86_64 AppImage on a Linux build host.

This command deliberately refuses to claim a Linux artifact from Windows or
macOS.  CI invokes it on a pinned Linux runner with Nuitka and appimagetool.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from backend.release import APP_VERSION, PRODUCT_NAME


class LinuxBuildError(RuntimeError):
    pass


def version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--channel", default="beta")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    output = args.output or _REPO / "dist" / "linux" / f"QuantumStudio-{APP_VERSION}-{args.channel}"
    output = output if output.is_absolute() else _REPO / output
    plan = {"platform": "linux", "architecture": "x86_64", "version": APP_VERSION, "channel": args.channel,
            "output": str(output), "format": "AppImage", "required_tools": ["Nuitka", "appimagetool"]}
    try:
        if args.dry_run:
            print(json.dumps({"status": "PLAN_ONLY", **plan}, indent=2)); return 0
        if not sys.platform.startswith("linux"):
            raise LinuxBuildError("LINUX_BUILD_HOST_REQUIRED: use --dry-run outside a Linux build host.")
        if platform.machine().lower() not in {"x86_64", "amd64"}:
            raise LinuxBuildError("LINUX_X86_64_BUILD_HOST_REQUIRED")
        appimagetool = shutil.which("appimagetool")
        if not appimagetool or not version("Nuitka"):
            raise LinuxBuildError("LINUX_APPIMAGE_TOOLCHAIN_MISSING: Nuitka and appimagetool are required.")
        if output.exists() and any(output.iterdir()):
            raise LinuxBuildError("Refusing to overwrite an existing Linux build directory.")
        output.mkdir(parents=True, exist_ok=False)
        nuitka_output = output / "nuitka"
        command = [sys.executable, "-m", "nuitka", "--standalone", "--enable-plugin=pyside6", "--output-dir=" + str(nuitka_output),
                   "--output-filename=QuantumStudio", "--product-name=" + PRODUCT_NAME, "--product-version=" + APP_VERSION,
                   "--file-description=" + PRODUCT_NAME, "--include-data-dir=" + str(_REPO / "assets") + "=assets",
                   "--include-package=backend.runtime", "--include-package=backend.update", "--include-package=backend.execution",
                   "--include-package=runtime_agent", str(_REPO / "frontend" / "main.py")]
        if subprocess.run(command, cwd=_REPO, shell=False, check=False).returncode:
            raise LinuxBuildError("NUITKA_FAILED")
        candidates = tuple(nuitka_output.glob("*.dist"))
        if len(candidates) != 1:
            raise LinuxBuildError("NUITKA_STANDALONE_OUTPUT_MISSING")
        appdir = output / "QuantumStudio.AppDir"; bundle = candidates[0]
        target = appdir / "usr" / "bin"; target.parent.mkdir(parents=True); shutil.copytree(bundle, target)
        desktop = appdir / "quantum-studio.desktop"
        desktop.write_text("[Desktop Entry]\nType=Application\nName=Quantum Studio\nExec=QuantumStudio\nIcon=quantum-studio\nCategories=Science;Education;\n", encoding="utf-8")
        shutil.copy2(_REPO / "assets" / "quantum-studio-v0.1.svg", appdir / "quantum-studio.svg")
        app_run = appdir / "AppRun"; app_run.write_text("#!/bin/sh\nexec \"$APPDIR/usr/bin/QuantumStudio\" \"$@\"\n", encoding="utf-8"); app_run.chmod(0o755)
        artifact = output / f"QuantumStudio-Linux-x86_64-{APP_VERSION}.AppImage"
        if subprocess.run([appimagetool, str(appdir), str(artifact)], cwd=output, shell=False, check=False).returncode:
            raise LinuxBuildError("APPIMAGETOOL_FAILED")
        (output / "build-provenance.json").write_text(json.dumps({"schema_version": 1, "product": PRODUCT_NAME, "version": APP_VERSION,
            "platform": "linux", "architecture": "x86_64", "python": platform.python_version(), "pyside6": version("PySide6"),
            "nuitka": version("Nuitka"), "build_timestamp": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "BUILT", **plan, "artifact": str(artifact)}, indent=2)); return 0
    except LinuxBuildError as error:
        print(f"LINUX_BUILD_ERROR: {error}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
