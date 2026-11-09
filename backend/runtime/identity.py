"""Single application identity source; safe when no Git checkout exists."""
from __future__ import annotations

import os
import platform
import sys
import subprocess
from datetime import datetime, timezone
from backend.release import APP_VERSION, DEFAULT_RELEASE_CHANNEL, PRODUCT_NAME as RELEASE_PRODUCT_NAME

PRODUCT_NAME = RELEASE_PRODUCT_NAME
VERSION = APP_VERSION
def _build_value(name, default):
    if getattr(sys,"frozen",False) or "__compiled__" in globals():
        try:
            import _quantumstudio_packaged_profile as pin
            return getattr(pin,name,default)
        except ImportError:return default
    return os.environ.get("QUANTUM_STUDIO_"+name,default)

BUILD_CHANNEL = _build_value("BUILD_CHANNEL", DEFAULT_RELEASE_CHANNEL)
BUILD_COMMIT = _build_value("BUILD_COMMIT", "")
BUILD_TIMESTAMP = _build_value("BUILD_TIMESTAMP", "")


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
