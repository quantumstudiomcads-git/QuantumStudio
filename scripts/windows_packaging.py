"""Qt-free Windows standalone build planning and package audits."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import platform as host_platform
import re
import shutil
from typing import Iterable

PRODUCT_NAME = "Quantum Studio"
EXECUTABLE_NAME = "QuantumStudio.exe"
PACKAGE_MARKER = "quantumstudio-build.json"
INSTALLER_INPUT = "quantumstudio-installer-input.json"
FORBIDDEN_PARTS = {"tests", ".git", ".venv", "venv", "venvs", "build", "__pycache__", "operator_tools", "licence_manager", "applicant_exports", "operator_data", "engine-pack", "engine_pack", "runtime-image", "runtime_image"}
FORBIDDEN_NAMES = {"pw.x", "ph.x", "q2r.x", "matdyn.x", "dynmat.x", "bands.x", "dos.x", "projwfc.x", "pp.x", "epsilon.x", "pw2wannier90.x", "epw.x", "wannier90.x", "bader", "engine-pack.json", "run_licence_manager.py", "licence.json", "receipt.json", "applicants.json", "audit.json", ".env", ".dev.vars", "id_rsa", "id_ed25519", "licence_manager_architecture.md", "licence_manager_operations.md", "licence_formats.md"}
FORBIDDEN_SUFFIXES = {".vhdx", ".sqlite", ".sqlite3", ".db", ".dpapi", ".p12", ".pfx", ".dev.vars", ".env", ".pem", ".key", ".secret", ".token"}
# These are the minimum application-level runtime artifacts.  An executable
# alone is a linked intermediate, not a usable Nuitka standalone product.
REQUIRED_STANDALONE_FILES = (
    EXECUTABLE_NAME,
    "assets/quantum-studio-v0.1.svg",
    "PySide6/qt-plugins/platforms/qwindows.dll",
    "cryptography/hazmat/bindings/_rust.pyd",
)
# MSVC appends _CL_ after its normal command line.  This overrides Nuitka's
# default /Ox for generated scientific modules that exhaust MSVC's optimizer.
MSVC_APPEND_OPTIONS = "/Od"

class WindowsBuildError(RuntimeError): pass

@dataclass(frozen=True)
class WindowsBuildPlan:
    repo: Path
    output: Path
    channel: str
    version: str
    commit: str
    dirty: bool
    architecture: str
    entry: Path
    icon_svg: Path
    icon_ico: Path
    nuitka_argv: tuple[str, ...]

    def manifest(self, *, python_version: str, pyside6_version: str, nuitka_version: str, timestamp: str | None = None) -> dict:
        return {"schema_version": 1, "product": PRODUCT_NAME, "version": self.version, "channel": self.channel,
                "platform": "windows", "architecture": self.architecture, "commit": self.commit,
                "dirty": self.dirty, "build_timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
                "python": python_version, "pyside6": pyside6_version, "nuitka": nuitka_version,
                "packaging_format": "nuitka-standalone", "entry_executable": EXECUTABLE_NAME,
                "resource_manifest": "assets/quantum-studio-v0.1.svg"}


def normalize_architecture(machine: str | None = None) -> str:
    value = (machine or host_platform.machine()).lower()
    if value in {"amd64", "x86_64", "x64"}: return "x86_64"
    raise WindowsBuildError(f"Unsupported Windows build architecture: {machine or value}. Only x86_64 is supported.")


def build_plan(*, repo: str | Path, output: str | Path, channel: str, version: str, commit: str, dirty: bool,
               python_executable: str, architecture: str = "x86_64") -> WindowsBuildPlan:
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", channel): raise WindowsBuildError("Build channel is invalid.")
    if architecture != "x86_64": raise WindowsBuildError("Windows build architecture must be x86_64.")
    entry, icon = repo / "frontend" / "main.py", repo / "assets" / "quantum-studio-v0.1.svg"
    if not entry.is_file(): raise WindowsBuildError("Canonical frontend entry point is missing.")
    if not icon.is_file(): raise WindowsBuildError("Canonical Quantum Studio artwork is missing.")
    ico = output / "build-assets" / "QuantumStudio.ico"
    argv = (python_executable, "-m", "nuitka", "--standalone", "--enable-plugin=pyside6", "--msvc=latest", "--jobs=4", "--windows-console-mode=disable", "--assume-yes-for-downloads",
            f"--output-dir={output}", f"--output-filename={EXECUTABLE_NAME}", f"--product-name={PRODUCT_NAME}",
            f"--file-description={PRODUCT_NAME}", f"--product-version={version}", f"--file-version={version}",
            f"--windows-icon-from-ico={ico}",
            f"--include-data-dir={repo / 'assets'}=assets", "--include-package=backend.runtime", "--include-package=backend.update", "--include-package=backend.execution",
            "--include-package=runtime_agent",
            "--include-module=scipy._external.array_api_compat.numpy.fft",
            "--nofollow-import-to=tests", "--nofollow-import-to=pytest", str(entry))
    return WindowsBuildPlan(repo, output, channel, version, commit, dirty, architecture, entry, icon, ico, argv)


def safe_clean_output(plan: WindowsBuildPlan) -> None:
    output = plan.output.resolve(); repo = plan.repo.resolve()
    if output == repo or output in {Path(output.anchor), repo.parent, Path.home().resolve()}:
        raise WindowsBuildError("Refusing to clean an unsafe Windows build output path.")
    marker = output / PACKAGE_MARKER
    if output.exists() and not marker.is_file(): raise WindowsBuildError("Refusing to clean an unrecognized output directory.")
    if output.exists(): shutil.rmtree(output)


def write_json(path: str | Path, payload: dict) -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path); return path


def installer_input_manifest(plan: WindowsBuildPlan, build_manifest: dict) -> dict:
    return {"schema_version": 1, "product": PRODUCT_NAME, "version": plan.version, "channel": plan.channel,
            "platform": "windows", "architecture": plan.architecture, "gui_bundle": {"path": "QuantumStudio.dist", "entry": EXECUTABLE_NAME},
            "runtime_image": {"status": "PENDING_W7", "descriptor": None},
            "runtime_agent": {"protocol_schema": 1, "status": "included-in-runtime-image"},
            "engine_pack": {"status": "PENDING_LEGAL_AND_W7", "descriptor": None},
            "licenses_notices": {"status": "PENDING_W7", "inputs": []}, "build_manifest": build_manifest}


def audit_package_contents(root: str | Path, *, max_file_size: int = 2 * 1024 * 1024 * 1024) -> dict:
    root = Path(root).absolute(); forbidden: list[str] = []; large: list[str] = []; files = 0; total = 0
    if not root.is_dir():
        return {"valid": False, "reason": "PACKAGE_MISSING", "forbidden": (), "missing_required": REQUIRED_STANDALONE_FILES,
                "file_count": 0, "total_bytes": 0, "large_files": ()}
    if root.is_symlink() or getattr(root.lstat(), "st_file_attributes", 0) & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        return {"valid": False, "reason": "PACKAGE_ROOT_REPARSE_POINT", "forbidden": ("PACKAGE_ROOT_REPARSE_POINT",),
                "missing_required": REQUIRED_STANDALONE_FILES, "file_count": 0, "total_bytes": 0, "large_files": ()}
    from scripts.package_exclusions import customer_package_exclusion_findings
    exclusion_findings = customer_package_exclusion_findings(root)
    resolved_root = root.resolve()
    for item in root.rglob("*"):
        relative = item.relative_to(root)
        attributes = getattr(item.lstat(), "st_file_attributes", 0)
        if item.is_symlink() or attributes & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            forbidden.append(relative.as_posix())
            continue
        try: item.resolve().relative_to(resolved_root)
        except ValueError: forbidden.append(relative.as_posix()); continue
        if any(part.casefold() in FORBIDDEN_PARTS for part in relative.parts) or item.name.casefold() in FORBIDDEN_NAMES or item.suffix.lower() in FORBIDDEN_SUFFIXES or "rootfs" in item.name.lower(): forbidden.append(relative.as_posix())
        if item.is_file():
            files += 1; size = item.stat().st_size; total += size
            if size > max_file_size: large.append(relative.as_posix())
    missing_required = tuple(path for path in REQUIRED_STANDALONE_FILES if not (root / path).is_file())
    if exclusion_findings:
        forbidden.extend(exclusion_findings)
    forbidden = sorted(set(forbidden))
    if missing_required:
        reason = "PACKAGE_INCOMPLETE"
    elif forbidden or large:
        reason = "FORBIDDEN_PACKAGE_CONTENT"
    else:
        reason = ""
    return {"valid": not missing_required and not forbidden and not large, "reason": reason,
            "forbidden": tuple(sorted(forbidden)), "missing_required": missing_required,
            "file_count": files, "total_bytes": total, "large_files": tuple(sorted(large))}
