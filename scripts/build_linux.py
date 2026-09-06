"""Reproducible Linux standalone build entry point for Quantum Studio."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import re
import shutil
import os
import subprocess
import sys
from pathlib import Path
import tempfile

IGNORE = "tests,.git,build,dist,software,backend/artifacts,validation,QuantumStudioValidation,.venv,.venv-build"


def bundle_linux_blas(output: Path) -> None:
    """Bundle the BLAS soname required by NumPy in standalone mode."""
    if sys.platform != "linux":
        return
    target = output / "libcblas.so.3"
    if target.exists():
        return
    candidates = (
        Path("/lib/x86_64-linux-gnu/libopenblas.so.0"),
        Path("/usr/lib/x86_64-linux-gnu/libopenblas.so.0"),
    )
    source = next((path for path in candidates if path.is_file()), None)
    if source is None:
        raise SystemExit(
            "STANDALONE_NATIVE_DEPENDENCY_MISSING: NumPy requires libcblas.so.3 "
            "and no system OpenBLAS provider was found."
        )
    shutil.copy2(source, target)

def write_standalone_launcher(output: Path, *, channel: str, commit: str, timestamp: str) -> None:
    """Provide the product-named entry point expected by desktop metadata."""
    launcher = output / "quantum-studio"
    launcher.write_text(
        f"#!/bin/sh\nexport QUANTUM_STUDIO_BUILD_CHANNEL={channel!r}\nexport QUANTUM_STUDIO_BUILD_COMMIT={commit!r}\nexport QUANTUM_STUDIO_BUILD_TIMESTAMP={timestamp!r}\nexec \"$(dirname \"$0\")/main.bin\" \"$@\"\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)


def resolve_deploy_tool() -> list[str]:
    sibling = Path(sys.executable).with_name("pyside6-deploy")
    if sibling.is_file() and sibling.stat().st_mode & 0o111:
        return [str(sibling)]
    candidate = shutil.which("pyside6-deploy")
    if candidate:
        return [candidate]
    try:
        subprocess.run([sys.executable, "-c", "import PySide6"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import importlib.util
        if importlib.util.find_spec("PySide6.scripts.deploy") is not None:
            return [sys.executable, "-m", "PySide6.scripts.deploy"]
    except (OSError, subprocess.SubprocessError):
        pass
    raise SystemExit("DEPLOY_TOOL_MISSING: install PySide6 deployment support in the active build environment (pyside6-deploy).")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("frontend/deployment"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--channel", default="beta-rc1")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output_root = (args.output if args.output.is_absolute() else repo / args.output).resolve()
    spec = (repo / "frontend" / "pysidedeploy.spec").read_text(encoding="utf-8")
    spec = re.sub(r"^input_file = .*?$", f"input_file = {repo / 'frontend' / 'main.py'}", spec, flags=re.MULTILINE)
    spec = re.sub(r"^project_dir = .*?$", f"project_dir = {repo}", spec, flags=re.MULTILINE)
    spec = re.sub(r"^exec_directory = .*?$", f"exec_directory = {output_root}", spec, flags=re.MULTILINE)
    with tempfile.NamedTemporaryFile("w", suffix=".spec", prefix="qs-b3-", delete=False, encoding="utf-8") as handle:
        handle.write(spec)
        spec_path = Path(handle.name)
    command = resolve_deploy_tool() + ["-c", str(spec_path), "--force", "--keep-deployment-files", "--name", "QuantumStudio", "--extra-ignore-dirs", IGNORE]
    if args.dry_run:
        command.append("--dry-run")
    print("Build Python:", sys.executable)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False, shell=False).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=False, shell=False).stdout.strip()
    build_env = os.environ.copy()
    build_env.update({"QUANTUM_STUDIO_BUILD_CHANNEL": args.channel, "QUANTUM_STUDIO_BUILD_COMMIT": commit + ("-DIRTY_BUILD" if dirty else ""), "QUANTUM_STUDIO_BUILD_TIMESTAMP": datetime.now(timezone.utc).isoformat()})
    print("Build channel:", args.channel)
    print("Build commit:", build_env["QUANTUM_STUDIO_BUILD_COMMIT"])
    print("Build command:", " ".join(command))
    print("Application-only build; scientific Engine Pack contents are excluded.")
    if args.dry_run:
        return subprocess.run(command, check=False, shell=False, env=build_env).returncode
    try:
        returncode = subprocess.run(command, check=False, shell=False, env=build_env).returncode
        if returncode == 0:
            package = output_root / "QuantumStudio.dist"
            built_package = package if package.is_dir() else repo / "frontend" / "deployment" / "QuantumStudio.dist"
            if not built_package.is_dir():
                raise SystemExit("STANDALONE_OUTPUT_MISSING: deployment completed without a standalone directory.")
            if built_package.resolve() != package.resolve():
                output_root.mkdir(parents=True, exist_ok=True)
                shutil.copytree(built_package, package, dirs_exist_ok=True)
            bundle_linux_blas(package)
            write_standalone_launcher(package, channel=args.channel, commit=build_env["QUANTUM_STUDIO_BUILD_COMMIT"], timestamp=build_env["QUANTUM_STUDIO_BUILD_TIMESTAMP"])
        return returncode
    finally:
        spec_path.unlink(missing_ok=True)

if __name__ == "__main__":
    raise SystemExit(main())
