"""Reproducible native Windows Nuitka build entry point for Quantum Studio."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path: sys.path.insert(0, str(_REPO))

try:
    from .windows_packaging import (EXECUTABLE_NAME, MSVC_APPEND_OPTIONS, PACKAGE_MARKER, WindowsBuildError, audit_package_contents,
                                    build_plan, generate_payload_inventory, installer_input_manifest, normalize_architecture, safe_clean_output, write_json)
except ImportError:  # direct script execution
    from windows_packaging import (EXECUTABLE_NAME, MSVC_APPEND_OPTIONS, PACKAGE_MARKER, WindowsBuildError, audit_package_contents,
                                   build_plan, generate_payload_inventory, installer_input_manifest, normalize_architecture, safe_clean_output, write_json)
from backend.runtime.identity import VERSION
from scripts.windows_profiles import build_profile, write_profile_assets, verify_built_profile, scan_secret_values, SECRET_BINDINGS
from backend.runtime.desktop_profile import DesktopProfileError, profile_bytes


def git_value(repo: Path, *arguments: str) -> str:
    try: return subprocess.run(["git", "-c", f"safe.directory={repo.resolve()}", *arguments], cwd=repo, capture_output=True, text=True, timeout=5, check=False, shell=False).stdout.strip()
    except (OSError, subprocess.SubprocessError): return ""


def dependency_version(name: str) -> str:
    try: return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError: return ""


def windows_build_environment(*, channel: str, commit: str, timestamp: str, inherited: dict[str, str] | None = None) -> dict[str, str]:
    """Return the controlled child environment for the MSVC standalone build."""
    environment = (os.environ if inherited is None else inherited).copy()
    for name in tuple(environment):
        if name in SECRET_BINDINGS or name.startswith(('OPERATOR_','QS_OPERATOR_','QS_SIGNING_','QS_LICENCE_SIGNING_','RESEND_','GOOGLE_','QS_ADMIN_','QUANTUM_STUDIO_UPDATE_SIGNING_')):
            environment.pop(name, None)
    environment.update({"QUANTUM_STUDIO_BUILD_CHANNEL": channel, "QUANTUM_STUDIO_BUILD_COMMIT": commit,
                        "QUANTUM_STUDIO_BUILD_TIMESTAMP": timestamp, "_CL_": MSVC_APPEND_OPTIONS})
    return environment


def generate_icon(svg: Path, ico: Path) -> None:
    """Create a build-local ICO from canonical artwork; never commits a derivative."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer
    except ImportError as error: raise WindowsBuildError("PySide6 QtSvg support is required to create the Windows icon.") from error
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid(): raise WindowsBuildError("Canonical SVG artwork cannot be rendered for the Windows icon.")
    image = QImage(256, 256, QImage.Format.Format_ARGB32); image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image); renderer.render(painter); painter.end()
    ico.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(ico), "ICO"): raise WindowsBuildError("Qt image codecs could not write the required ICO icon.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("local","staging","production"), required=True)
    parser.add_argument("--config", type=Path, help="Reviewed public profile JSON; staging/production only.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--channel", default="beta")
    parser.add_argument("--dry-run", action="store_true", help="Print a Windows build plan; allowed from non-Windows hosts.")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    output = (args.output or Path("dist") / "windows" / f"QuantumStudio-{VERSION}-{args.profile}-{args.channel}")
    output = output if output.is_absolute() else repo / output
    is_windows = sys.platform.startswith("win")
    try:
        public_profile = build_profile(repo,args.profile,args.config)
        architecture = normalize_architecture(platform.machine())
        commit, dirty = git_value(repo, "rev-parse", "HEAD"), bool(git_value(repo, "status", "--porcelain"))
        plan = build_plan(repo=repo, output=output, channel=args.channel, version=VERSION, commit=commit, dirty=dirty,
                          python_executable=sys.executable, architecture=architecture, desktop_profile=public_profile)
        if args.dry_run:
            print(json.dumps({"status": "PLAN_ONLY", "host_windows": is_windows, "argv": list(plan.nuitka_argv),
                              "output": str(plan.output), "entry": str(plan.entry), "profile":public_profile,
                              "profile_sha256":__import__("hashlib").sha256(profile_bytes(public_profile)).hexdigest(),"updates":"enabled" if public_profile.get("updates",{}).get("enabled") else "disabled"}, indent=2)); return 0
        if not is_windows: raise WindowsBuildError("WINDOWS_BUILD_HOST_REQUIRED: use --dry-run on non-Windows hosts.")
        if not commit: raise WindowsBuildError("GIT_COMMIT_UNAVAILABLE: a real Windows build requires an exact source revision.")
        if dirty and args.channel not in {"development", "dev"}: raise WindowsBuildError("Refusing a dirty beta/release Windows build.")
        if args.clean: safe_clean_output(plan)
        if plan.output.exists() and any(plan.output.iterdir()): raise WindowsBuildError("Build output already exists; use --clean only for a recognized prior Quantum Studio build.")
        if not dependency_version("Nuitka"): raise WindowsBuildError("NUITKA_MISSING: install build-only Nuitka in the Windows build environment.")
        if not dependency_version("PySide6"): raise WindowsBuildError("PYSIDE6_MISSING: install runtime dependencies in the Windows build environment.")
        generate_icon(plan.icon_svg, plan.icon_ico)
        environment = windows_build_environment(channel=args.channel, commit=commit + ("-DIRTY_BUILD" if dirty else ""),
                                                timestamp=datetime.now(timezone.utc).isoformat())
        # Public resource and executable-bound pin are generated only in the owned build output.
        write_profile_assets(plan,environment)
        completed = subprocess.run(list(plan.nuitka_argv), cwd=repo, env=environment, shell=False, check=False)
        if completed.returncode != 0: raise WindowsBuildError(f"NUITKA_FAILED: exited with {completed.returncode}.")
        bundle = plan.output / "main.dist"
        if not bundle.is_dir():
            candidates = tuple(plan.output.glob("*.dist")); bundle = candidates[0] if len(candidates) == 1 else bundle
        if not bundle.is_dir(): raise WindowsBuildError("STANDALONE_OUTPUT_MISSING: Nuitka produced no standalone bundle.")
        audit = audit_package_contents(bundle)
        if not audit["valid"]:
            details = tuple(audit.get("missing_required", ())) + tuple(audit["forbidden"]) + tuple(audit["large_files"])
            raise WindowsBuildError("PACKAGE_AUDIT_FAILED: " + audit["reason"] + (": " + ", ".join(details) if details else ""))
        verify_built_profile(bundle,plan)
        scan_secret_values(bundle)
        manifest = plan.manifest(python_version=platform.python_version(), pyside6_version=dependency_version("PySide6"), nuitka_version=dependency_version("Nuitka"), timestamp=environment["QUANTUM_STUDIO_BUILD_TIMESTAMP"])
        write_json(bundle / PACKAGE_MARKER, manifest); write_json(bundle / "quantumstudio-installer-input.json", installer_input_manifest(plan, manifest))
        inventory = generate_payload_inventory(bundle, manifest, generated_at=environment["QUANTUM_STUDIO_BUILD_TIMESTAMP"])
        final_audit = audit_package_contents(bundle)
        if not final_audit["valid"]:
            raise WindowsBuildError("FINAL_PACKAGE_AUDIT_FAILED: " + final_audit["reason"])
        print(json.dumps({"status": "BUILT", "bundle": str(bundle), "manifest": manifest,
                          "inventory_files": len(inventory["files"]), "audit": final_audit}, indent=2)); return 0
    except (WindowsBuildError, DesktopProfileError) as error:
        print(f"WINDOWS_BUILD_ERROR: {error}", file=sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
