"""Audit only declared offline installer payloads before a privileged build."""
from __future__ import annotations
from pathlib import Path

FORBIDDEN_PARTS = {".git", "tests", ".venv", "venv", "__pycache__"}
FORBIDDEN_SUFFIXES = {".vhdx"}
FORBIDDEN_ENGINE_NAMES = {"pw.x", "ph.x", "q2r.x", "matdyn.x", "dynmat.x", "bands.x", "dos.x", "projwfc.x", "pp.x", "epsilon.x", "pw2wannier90.x", "epw.x", "wannier90.x", "bader"}


def audit_installer_payload(root: str | Path, *, declared: tuple[str | Path, ...]) -> dict[str, object]:
    root = Path(root).resolve()
    allowed = {Path(item).resolve() for item in declared}
    forbidden: list[str] = []
    if not root.is_dir():
        return {"valid": False, "reason": "PAYLOAD_ROOT_MISSING", "forbidden": ()}
    for item in root.rglob("*"):
        relative = item.relative_to(root)
        declared_item = any(item == candidate or candidate in item.parents for candidate in allowed)
        name = item.name.lower()
        if any(part in FORBIDDEN_PARTS for part in relative.parts): forbidden.append(relative.as_posix())
        if item.suffix.lower() in FORBIDDEN_SUFFIXES or "rootfs" in name or item.name in FORBIDDEN_ENGINE_NAMES:
            if not declared_item: forbidden.append(relative.as_posix())
    return {"valid": not forbidden, "reason": "" if not forbidden else "FORBIDDEN_INSTALLER_CONTENT", "forbidden": tuple(sorted(set(forbidden)))}
