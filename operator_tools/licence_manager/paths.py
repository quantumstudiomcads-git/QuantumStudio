"""Operator-owned local storage locations."""
from __future__ import annotations

import os
from pathlib import Path


def data_root(override: str | Path | None = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()
    if os.name != "nt":
        raise RuntimeError("Production licence-manager storage is available only on Windows.")
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("Windows local application-data location is unavailable.")
    return Path(base) / "QuantumStudio" / "LicenceManager"
