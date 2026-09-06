"""Single application identity source; safe when no Git checkout exists."""
from __future__ import annotations

import os
import platform
import subprocess
from datetime import datetime, timezone

PRODUCT_NAME = "Quantum Studio"
VERSION = "0.2.0"
BUILD_CHANNEL = os.environ.get("QUANTUM_STUDIO_BUILD_CHANNEL", "development")
BUILD_COMMIT = os.environ.get("QUANTUM_STUDIO_BUILD_COMMIT", "")
BUILD_TIMESTAMP = os.environ.get("QUANTUM_STUDIO_BUILD_TIMESTAMP", "")


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=1, check=False, shell=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def build_identity() -> dict[str, str]:
    return {
        "product": PRODUCT_NAME,
        "version": VERSION,
        "channel": BUILD_CHANNEL,
        "commit": BUILD_COMMIT or _git_commit(),
        "build_timestamp": BUILD_TIMESTAMP,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
