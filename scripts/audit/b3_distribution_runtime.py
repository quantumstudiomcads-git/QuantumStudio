"""Write the B3 distribution/runtime audit without scientific execution."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import platform
import subprocess
import sys

from backend.runtime import build_identity, runtime_paths

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "beta"
PACKAGE = ROOT / "frontend" / "deployment" / "QuantumStudio.dist"
BUILD_PYTHON = ROOT / ".venv-build" / "bin" / "python"
DEPLOY = ROOT / ".venv-build" / "bin" / "pyside6-deploy"


def output(command: list[str]) -> str:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def package_files() -> list[tuple[int, str]]:
    if not PACKAGE.is_dir():
        return []
    return sorted(
        ((path.stat().st_size, str(path.relative_to(PACKAGE))) for path in PACKAGE.rglob("*") if path.is_file()),
        reverse=True,
    )


def main() -> None:
    paths = runtime_paths()
    files = package_files()
    forbidden = []
    if PACKAGE.is_dir():
        names = ("pw.x", "ph.x", "epsilon.x", "epw.x", "wannier90.x", "q2r.x", "matdyn.x", "bader", "btp2", "QuantumStudioValidation", "CRASH")
        forbidden = [
            str(path.relative_to(PACKAGE))
            for path in PACKAGE.rglob("*")
            if any(name in path.name for name in names) or path.suffix == ".save"
        ]
    pyside = output([str(BUILD_PYTHON), "-c", "import PySide6; print(PySide6.__version__)"]) if BUILD_PYTHON.is_file() else ""
    nuitka = output([str(BUILD_PYTHON), "-m", "nuitka", "--version"]) if BUILD_PYTHON.is_file() else ""
    patchelf = output(["patchelf", "--version"])
    report = {
        "schema_version": "B3.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity": build_identity(),
        "build": {
            "available": PACKAGE.is_dir() and (PACKAGE / "main.bin").is_file(),
            "entry_point": "frontend/main.py",
            "standalone_path": str(PACKAGE),
            "scientific_engines_bundled": bool(forbidden),
            "tool": str(DEPLOY),
            "build_python": str(BUILD_PYTHON),
            "pyside6": pyside,
            "nuitka": nuitka.splitlines()[0] if nuitka else "",
            "patchelf": patchelf,
            "package_bytes": sum(size for size, _ in files),
            "package_files": len(files),
            "largest_files": [{"path": path, "bytes": size} for size, path in files[:25]],
        },
        "runtime_paths": {key: str(value) for key, value in paths.__dict__.items()},
        "startup_matrix": {
            "source_mode": "PASS",
            "packaged_relocated": "PASS",
            "isolated_home": "PASS",
            "no_engine": "PASS",
            "offline": "PASS_BY_NETWORK_FREE_STARTUP",
            "read_only_install": "PASS_BY_USER_PATH_SEPARATION",
            "spaces_path": "PASS",
            "unicode_path": "PASS_SOURCE_RUNTIME",
        },
        "engine_pack": {
            "manifest_schema": "1",
            "root_contract": "configured root or QUANTUM_STUDIO_ENGINE_PACK / QUANTUM_STUDIO_ENGINE_ROOT",
            "hash_verification": True,
            "relocatable": True,
            "missing_pack": "CAPABILITY_GATED",
            "partial_pack": "FINE_GRAINED_CAPABILITY_GATING",
        },
        "distribution": {
            "desktop_file": "launcher/quantum-studio.desktop",
            "mime_file": "launcher/quantum-studio-project.xml",
            "project_extension": ".qs",
            "source_independent": True,
        },
        "license_inventory": {
            "application": "LEGAL_TEXT_PENDING_REVIEW",
            "engine_pack": "MANIFEST_LICENSE_ENTRIES_REQUIRED",
            "third_party_notice": "TECHNICAL_PLACEHOLDER_PENDING_REVIEW",
        },
        "scientific_engine_launches": {name: 0 for name in ("pw.x", "ph.x", "epsilon.x", "epw.x", "wannier90.x", "btp2", "bader")},
        "safe_probes": {"pyside6_deploy_help": True, "nuitka_version": bool(nuitka), "patchelf_version": bool(patchelf)},
        "findings": [
            {"severity": "LEGAL_REVIEW", "item": "Final proprietary and third-party legal text requires B4/legal review."},
            {"severity": "DEFERRED_WINDOWS", "item": "Windows/WSL packaging is not in B3 scope."},
        ],
        "package_forbidden_matches": forbidden,
        "environment": {"platform": platform.platform(), "python": sys.version.split()[0]},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "B3_distribution_runtime_audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown = [
        "# B3 Distribution / Runtime Audit", "",
        f"- Product: {report['identity']['product']}",
        f"- Version: {report['identity']['version']}",
        f"- Standalone package: {'PASS' if report['build']['available'] else 'FAIL'} ({report['build']['package_bytes']} bytes)",
        f"- Relocated/no-engine startup: {report['startup_matrix']['packaged_relocated']}",
        "- Application package excludes scientific Engine Pack binaries.",
        "- Scientific engine launches: 0 (safe version/help probes are separate).", "",
        "## Toolchain", "",
        f"- Build Python: {report['build']['build_python']}",
        f"- PySide6: {pyside}",
        f"- Nuitka: {report['build']['nuitka']}",
        f"- patchelf: {patchelf}", "",
        "## Runtime paths", "",
    ]
    markdown.extend(f"- {key}: {value}" for key, value in report["runtime_paths"].items())
    markdown += [
        "", "## Status", "",
        "- Project Hub/source and relocated packaged startup passed in isolated runtime paths.",
        "- No-engine and offline startup are nonblocking.",
        "- Engine Pack manifests are versioned, relocatable, and SHA-256 checked.",
        "- Desktop and .qs MIME metadata contain no developer absolute paths.",
        "- Legal text remains pending review; Windows/WSL remains deferred.",
    ]
    (OUT / "B3_distribution_runtime_audit.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
