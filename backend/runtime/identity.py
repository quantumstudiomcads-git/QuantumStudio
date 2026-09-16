"""Single application identity source; safe when no Git checkout exists."""
from __future__ import annotations

import os
import platform
import subprocess
from datetime import datetime, timezone
from backend.release import APP_VERSION, DEFAULT_RELEASE_CHANNEL, PRODUCT_NAME as RELEASE_PRODUCT_NAME

PRODUCT_NAME = RELEASE_PRODUCT_NAME
VERSION = APP_VERSION
BUILD_CHANNEL = os.environ.get("QUANTUM_STUDIO_BUILD_CHANNEL", DEFAULT_RELEASE_CHANNEL)
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
