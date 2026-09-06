"""Deterministic collection of QE/PHonon artifacts for EPW 6.1."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import shutil

class EPWArtifactError(ValueError):
    pass

@dataclass(frozen=True)
class EPWArtifact:
    source: str
    destination: str
    size: int
    sha256: str

def _file(path: Path, label: str) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        raise EPWArtifactError(f"Missing or empty EPW {label}: {path}")
    return path

def _entry(source: Path, destination: Path) -> EPWArtifact:
    data = destination.read_bytes()
    return EPWArtifact(str(source), str(destination), len(data), hashlib.sha256(data).hexdigest())

def collect_epw_phonon_artifacts(source_phonon_root, prefix, nq_irred, destination_save, *, source_dyn_root=None):
    """Collect the exact EPW 6.1 ``pp.py`` layout without shell commands."""
    source = Path(source_phonon_root).resolve()
    destination = Path(destination_save).resolve()
    if not isinstance(nq_irred, int) or nq_irred < 1:
        raise EPWArtifactError("nq_irred must be a positive integer.")
    if not source.is_dir():
        raise EPWArtifactError(f"EPW phonon source directory is missing: {source}")
    phroot = source / "_ph0"
    if not phroot.is_dir():
        phroot = source / "qe_out" / "_ph0"
    if not phroot.is_dir():
        phroot = source / "scf" / "_ph0"
    if not phroot.is_dir():
        raise EPWArtifactError(f"EPW phonon scratch directory is missing below: {source}")
    phsave = _file(phroot / f"{prefix}.phsave" / "control_ph.xml", "phsave/control_ph.xml")
    destination.mkdir(parents=True, exist_ok=True)
    dyn_source = Path(source_dyn_root).resolve() if source_dyn_root is not None else source
    entries = []
    names = set()
    for index in range(1, nq_irred + 1):
        dyn = _file(dyn_source / f"{prefix}.dyn{index}", f"dynamical matrix q{index}")
        dvscf_root = phroot if index == 1 else phroot / f"{prefix}.q_{index}"
        dvscf = _file(dvscf_root / f"{prefix}.dvscf1", f"dvscf q{index}")
        target_dyn = destination / f"{prefix}.dyn_q{index}"
        target_dv = destination / f"{prefix}.dvscf_q{index}"
        for source_path, target in ((dyn, target_dyn), (dvscf, target_dv)):
            if target.name in names or target.exists():
                raise EPWArtifactError(f"EPW destination collision: {target}")
            names.add(target.name)
            shutil.copy2(source_path, target)
            entries.append(_entry(source_path, target))
    target_phsave = destination / f"{prefix}.phsave"
    if not target_phsave.exists():

        shutil.copytree(phsave.parent, target_phsave)
    for path in sorted(target_phsave.rglob("*")):
        if path.is_file():
            entries.append(_entry(target_phsave / path.relative_to(target_phsave), path))
    return {"prefix": prefix, "nq_irred": nq_irred, "source": str(source), "destination": str(destination), "artifacts": tuple(entries)}
