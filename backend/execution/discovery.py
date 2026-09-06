"""Safe, machine-local Quantum ESPRESSO installation discovery."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import subprocess
from typing import Iterable

QE_TOOLS = (
    "pw.x", "ph.x", "bands.x", "dos.x", "projwfc.x", "pp.x", "q2r.x",
    "matdyn.x", "pw2wannier90.x", "fs.x", "hp.x", "neb.x", "cp.x", "epw.x",
)


@dataclass(frozen=True)
class QuantumEspressoInstallation:
    bin_directory: str
    version: str
    tools: dict[str, str]
    source: str

    @property
    def pw_path(self) -> str:
        return self.tools["pw.x"]


@dataclass(frozen=True)
class ToolDiscoveryResult:
    installations: tuple[QuantumEspressoInstallation, ...]
    searched_roots: tuple[str, ...]

    @property
    def preferred(self) -> QuantumEspressoInstallation | None:
        return self.installations[0] if self.installations else None


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version)) or (0,)


def _parse_version(output: str) -> str | None:
    if not re.search(r"quantum\s+espresso|pwscf", output, re.I):
        return None
    patterns = (
        r"(?:quantum\s+espresso|pwscf)[^\d]{0,40}(\d+\.\d+(?:\.\d+)?)",
        r"\bv\.?\s*(\d+\.\d+(?:\.\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, output, re.I | re.S)
        if match:
            return match.group(1)
    return None


def validate_qe_installation(candidate: str | Path, *, timeout: float = 2.0, source: str = "manual") -> QuantumEspressoInstallation | None:
    """Validate a QE bin directory, pw.x file, or QE root without shell execution."""
    path = Path(candidate).expanduser()
    if path.is_dir():
        bin_dir = path / "bin" if (path / "bin" / "pw.x").is_file() else path
        pw = bin_dir / "pw.x"
    else:
        pw = path
        bin_dir = pw.parent
    if pw.name != "pw.x" or not pw.is_file() or not os.access(pw, os.X_OK):
        return None
    try:
        result = subprocess.run(
            [str(pw), "-version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, timeout=timeout, shell=False, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    version = _parse_version((result.stdout or "") + "\n" + (result.stderr or ""))
    if version is None:
        return None
    tools = {}
    for name in QE_TOOLS:
        item = bin_dir / name
        if item.is_file() and os.access(item, os.X_OK):
            tools[name] = str(item.resolve())
    if "pw.x" not in tools:
        return None
    return QuantumEspressoInstallation(str(bin_dir.resolve()), version, tools, source)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _known_candidates(existing_directory: str | None = None, environment: dict[str, str] | None = None) -> tuple[tuple[Path, str], ...]:
    candidates: list[tuple[Path, str]] = []
    if existing_directory:
        candidates.append((Path(existing_directory), "saved"))
    path_value = (environment or {}).get("PATH") or os.environ.get("PATH", "")
    found = shutil.which("pw.x", path=path_value)
    if found:
        candidates.append((Path(found), "PATH"))
    repo = _repo_root()
    patterns = (
        "software/engines/qe/*/bin/pw.x", "software/qe/*/bin/pw.x", "software/**/bin/pw.x",
    )
    for pattern in patterns:
        for item in sorted(repo.glob(pattern))[:128]:
            candidates.append((item, "repository"))
    home = Path.home()
    for root in (home / "bin", home / ".local/bin", home / "software", home / "Software", home / "apps", home / "Applications", home / "QuantumStudio", home / "Desktop"):
        if root.is_dir():
            candidates.extend((item, "user") for item in sorted(root.glob("*/bin/pw.x"))[:128])
            candidates.extend((item, "user") for item in sorted(root.glob("*/software/engines/qe/*/bin/pw.x"))[:128])
            candidates.extend((item, "user") for item in sorted(root.glob("software/engines/qe/*/bin/pw.x"))[:128])
    for root in (Path("/usr/bin"), Path("/usr/local/bin"), Path("/opt"), Path("/opt/local"), Path("/usr/local"), Path("/apps"), Path("/software")):
        if root.is_dir():
            candidates.extend((item, "system") for item in sorted(root.glob("*/bin/pw.x"))[:128])
    return tuple(candidates)


def _bounded_deep_candidates(roots: Iterable[Path], *, max_depth: int = 5, max_directories: int = 5000) -> tuple[Path, ...]:
    found: list[Path] = []
    seen = 0
    for root in roots:
        if not root.is_dir():
            continue
        for directory, children, filenames in os.walk(root, followlinks=False):
            seen += 1
            if seen > max_directories:
                return tuple(found)
            relative = Path(directory).relative_to(root)
            if len(relative.parts) >= max_depth:
                children[:] = []
            if "pw.x" in filenames:
                found.append(Path(directory) / "pw.x")
    return tuple(found)


def discover_bader(**kwargs):
    """Discover Bader from PATH and shared Quantum Studio engine roots."""
    environment=kwargs.get("environment") or {}
    path_value=environment.get("PATH") or os.environ.get("PATH", "")
    candidates=[]
    found=shutil.which("bader", path=path_value)
    if found: candidates.append(Path(found))
    home=Path.home(); repo=_repo_root()
    for root in (repo, home / "QuantumStudio", home / "software", home / "Software", home / "Desktop"):
        if root.is_dir():
            candidates.extend(root.glob("**/software/engines/bader/*/bader"))
            candidates.extend(root.glob("**/engines/bader/*/bader"))
    return tuple(dict.fromkeys(str(item.resolve()) for item in candidates if item.is_file() and os.access(item, os.X_OK)))


def discover_boltztrap2(*, environment: dict[str, str] | None = None) -> tuple[str, ...]:
    environment = environment or {}
    path_value = environment.get("PATH") or os.environ.get("PATH", "")
    candidates = []
    found = shutil.which("btp2", path=path_value)
    if found: candidates.append(Path(found))
    repo = _repo_root()
    candidates.extend(repo.glob("software/engines/boltztrap2/*/bin/btp2"))
    candidates.extend(repo.glob("software/engines/bin/btp2"))
    home = Path.home()
    for root in (home / "QuantumStudio", home / "software", home / "Software", home / "Desktop"):
        if root.is_dir(): candidates.extend(root.glob("**/software/engines/boltztrap2/*/bin/btp2"))
    return tuple(dict.fromkeys(str(item.resolve()) for item in candidates if item.is_file() and os.access(item, os.X_OK)))

def discover_quantum_espresso(*, existing_directory: str | None = None, environment: dict[str, str] | None = None, deep: bool = False) -> ToolDiscoveryResult:
    """Discover local QE installs, ranking exact 7.6 first then highest version."""
    candidates = list(_known_candidates(existing_directory, environment))
    searched = [str(path) for path, _ in candidates]
    if deep:
        repo = _repo_root()
        home = Path.home()
        roots = (repo / "software", home / "software", home / "Software", home / "apps", home / "QuantumStudio", Path("/opt"), Path("/apps"), Path("/software"))
        candidates.extend((item, "deep") for item in _bounded_deep_candidates(roots))
        searched.extend(str(root) for root in roots if root.is_dir())
    installations = {}
    for candidate, source in candidates:
        installation = validate_qe_installation(candidate, source=source)
        if installation:
            installations[installation.bin_directory] = installation
    source_rank = {"saved": 0, "PATH": 1, "repository": 2, "user": 3, "system": 4, "deep": 5}
    ranked = sorted(
        installations.values(),
        key=lambda item: (0 if item.version.startswith("7.6") else 1, tuple(-part for part in _version_key(item.version)), source_rank.get(item.source, 99), item.bin_directory),
    )
    return ToolDiscoveryResult(tuple(ranked), tuple(dict.fromkeys(searched)))
