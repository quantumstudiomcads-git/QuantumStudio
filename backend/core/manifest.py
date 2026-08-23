"""
Quantum Studio Calculation Manifest

The manifest is the canonical, portable description of a calculation.

It must contain enough information to reproduce the calculation on:
    - the local machine
    - a remote machine
    - an HPC system

The GUI describes WHAT the user wants to calculate.
The backend determines HOW that calculation is executed.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_VERSION = "1.0"


def create_manifest(
    *,
    workflow: str,
    structure: dict[str, Any],
    parameters: dict[str, Any] | None = None,
    execution_target: str = "local",
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create a canonical Quantum Studio calculation manifest.
    """

    calculation_id = str(uuid.uuid4())

    manifest = {
        "quantum_studio": {
            "manifest_version": MANIFEST_VERSION,
        },

        "calculation": {
            "id": calculation_id,
            "workflow": workflow,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "status": "created",
        },

        "structure": structure,

        "parameters": parameters or {},

        "dependencies": dependencies or [],

        "execution": {
            "target": execution_target,
        },

        "engine": {
            "resolved": None,
            "version": None,
        },

        "artifacts": {
            "directory": None,
            "inputs": [],
            "outputs": [],
            "results": None,
        },
    }

    return manifest


def save_manifest(
    manifest: dict[str, Any],
    path: str | Path,
) -> Path:
    """
    Save a manifest as formatted JSON.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            manifest,
            handle,
            indent=2,
            sort_keys=False,
        )

    return path


def load_manifest(
    path: str | Path,
) -> dict[str, Any]:
    """
    Load a Quantum Studio calculation manifest.
    """

    path = Path(path)

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        return json.load(handle)
