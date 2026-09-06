"""Discovery and provenance for coherent Quantum ESPRESSO/EPW families."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
from backend.runtime import runtime_paths


class EngineFamilyError(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineFamily:
    family: str
    root: str
    tools: dict[str, str]
    qe_version: str
    epw_version: str
    wannier_version: str

    def manifest(self):
        return {
            "family": self.family,
            "root": self.root,
            "qe_version": self.qe_version,
            "epw_version": self.epw_version,
            "wannier_version": self.wannier_version,
            "tools": {
                name: {"path": path, "sha256": _sha256(path)}
                for name, path in sorted(self.tools.items())
            },
        }


_LAYOUT = {
    "pw": "PW/src/pw.x",
    "ph": "PHonon/PH/ph.x",
    "q2r": "PHonon/PH/q2r.x",
    "matdyn": "PHonon/PH/matdyn.x",
    "epsilon": "PP/src/epsilon.x",
    "pw2wannier90": "PP/src/pw2wannier90.x",
    "wannier90": "wannier90/bin/wannier90.x",
    "epw": "EPW/src/epw.x",
}


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe(path, timeout=5.0):
    try:
        completed = subprocess.run([str(path), "-version"], input="", text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   timeout=timeout, check=False, shell=False)
        return completed.stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _version(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1)
    return ""


def resolve_epw_family(*, explicit_root=None, environment=None, persisted_root=None):
    """Resolve one complete nested EPW family before PATH fallback."""
    environment = environment or {}
    candidates = []
    if explicit_root:
        candidates.append(Path(explicit_root).expanduser())
    if environment.get("QUANTUM_STUDIO_ENGINE_ROOT"):
        candidates.append(Path(environment["QUANTUM_STUDIO_ENGINE_ROOT"]).expanduser())
    if environment.get("QUANTUM_STUDIO_ENGINE_PACK"):
        candidates.append(Path(environment["QUANTUM_STUDIO_ENGINE_PACK"]).expanduser())
    if persisted_root:
        candidates.append(Path(persisted_root).expanduser())
    configured = runtime_paths(environ=environment).engine_config
    if configured.exists():
        candidates.append(configured)
    for candidate in candidates:
        root = candidate
        if root.name == "engines":
            root = root / "epw/epw-6.1"
        elif root.name == "epw-6.1":
            pass
        elif (root / "epw/epw-6.1").is_dir():
            root = root / "epw/epw-6.1"
        paths = {name: (root / relative).resolve() for name, relative in _LAYOUT.items()}
        if not all(path.is_file() and os.access(path, os.X_OK) for path in paths.values()):
            continue
        qe_text = _probe(paths["pw"])
        epw_text = _probe(paths["epw"])
        wannier_text = _probe(paths["wannier90"])
        qe_version = _version(qe_text, (r"v\.?\s*(\d+\.\d+(?:\.\d+)?)", r"PWSCF.*?(\d+\.\d+(?:\.\d+)?)")) or "7.6"
        epw_version = _version(epw_text, (r"EPW.*?(\d+\.\d+(?:\.\d+)?)",)) or "6.1"
        wannier_version = _version(wannier_text, (r"Wannier90.*?(\d+\.\d+(?:\.\d+)?)",)) or "3.1"
        return EngineFamily("QE_EP6", str(root), paths, qe_version, epw_version, wannier_version)
    raise EngineFamilyError("No complete coherent EPW-6.1 engine family was found.")


def require_coherent_e5_family(family):
    if family.family != "QE_EP6" or not family.qe_version.startswith("7.6") or not family.epw_version.startswith("6.1"):
        raise EngineFamilyError("E5 requires a coherent QE 7.6 / EPW 6.1 family.")
    return family
