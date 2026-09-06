"""Discovery for the isolated BoltzTraP2 command-line environment."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess


@dataclass(frozen=True)
class BoltzTraP2Installation:
    executable: str
    version: str
    source: str


def discover(*, environment: dict[str, str] | None = None) -> BoltzTraP2Installation | None:
    environment = environment or {}
    path_value = environment.get("PATH") or os.environ.get("PATH", "")
    candidates: list[tuple[Path, str]] = []
    found = shutil.which("btp2", path=path_value)
    if found: candidates.append((Path(found), "PATH"))
    repo = Path(__file__).resolve().parents[3]
    candidates.extend((item, "repository") for item in repo.glob("software/engines/boltztrap2/*/bin/btp2"))
    candidates.extend((item, "repository") for item in repo.glob("software/engines/bin/btp2"))
    for candidate, source in candidates:
        if not candidate.is_file() or not os.access(candidate, os.X_OK): continue
        try:
            probe = subprocess.run([str(candidate), "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5, shell=False, check=False)
        except (OSError, subprocess.TimeoutExpired): continue
        text = probe.stdout or ""
        if "BoltzTraP2" not in text: continue
        version = text.strip().split("BoltzTraP2", 1)[-1].strip().splitlines()[0].strip()
        return BoltzTraP2Installation(str(candidate.resolve()), version, source)
    return None
