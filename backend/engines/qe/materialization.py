"""Self-contained, workflow-local QE pseudopotential materialization."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping

from backend.pseudopotentials.models import sha256


class PseudopotentialMaterializationError(RuntimeError):
    """Raised when selected pseudo provenance cannot be copied safely."""


def _copy_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{destination.name}.", dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def materialize_workflow_pseudopotentials(workflow_root: str | Path, pseudopotentials: Mapping[str, object]) -> dict[str, dict[str, str]]:
    """Copy the already-selected pseudo set once into ``workflow_root/pseudos``."""
    root = Path(workflow_root).resolve()
    pseudo_root = root / "pseudos"
    materials: dict[str, dict[str, str]] = {}
    by_filename: dict[str, str] = {}
    for element, raw in pseudopotentials.items():
        if not isinstance(raw, Mapping):
            raise PseudopotentialMaterializationError(f"Pseudopotential provenance for {element!r} is invalid.")
        filename = str(raw.get("filename", "")).strip()
        if not filename or Path(filename).name != filename:
            raise PseudopotentialMaterializationError(f"Pseudopotential filename for {element!r} is unsafe.")
        source_value = raw.get("source")
        source = Path(str(source_value)).expanduser() if source_value else None
        expected_hash = raw.get("sha256")
        if source is None or not source.is_file():
            workflow_copy = pseudo_root / filename
            if workflow_copy.is_file() and (not expected_hash or sha256(workflow_copy)==expected_hash):
                source = workflow_copy
            else:
                raise PseudopotentialMaterializationError(f"Selected pseudopotential source is missing: {filename}")
        source_hash = sha256(source)
        if expected_hash and source_hash != expected_hash:
            raise PseudopotentialMaterializationError(f"Selected pseudopotential SHA-256 does not match provenance: {filename}")
        prior_hash = by_filename.get(filename)
        if prior_hash is not None and prior_hash != source_hash:
            raise PseudopotentialMaterializationError(f"Pseudopotential basename provenance conflict: {filename}")
        destination = pseudo_root / filename
        if prior_hash is None:
            _copy_atomic(source, destination)
            destination_hash = sha256(destination)
            if destination_hash != source_hash:
                raise PseudopotentialMaterializationError(f"Workflow pseudopotential copy failed integrity verification: {filename}")
            by_filename[filename] = source_hash
        materials[str(element)] = {
            "filename": filename,
            "relative_path": (Path("pseudos") / filename).as_posix(),
            "sha256": source_hash,
            "source": str(source),
        }
    return materials
