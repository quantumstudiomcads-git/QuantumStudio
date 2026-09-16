"""Non-secret client configuration and per-user release-channel selection."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from backend.release import APP_VERSION, DEFAULT_RELEASE_CHANNEL, RUNTIME_SCHEMA_VERSION
from backend.runtime.paths import runtime_paths
from .client import UpdateClient
from .signing import b64url_decode, UpdateVerifier
from .transport import HttpsUpdateSource


def platform_record(*, platform_name: str | None = None) -> str:
    name = platform_name or sys.platform
    if name.startswith("win"):
        return "windows-x86_64"
    if name.startswith("linux"):
        return "linux-x86_64"
    return "unsupported"


def selected_channel(*, paths=None) -> str:
    paths = paths or runtime_paths()
    try:
        value = json.loads((paths.config / "update-settings.json").read_text(encoding="utf-8")).get("channel", DEFAULT_RELEASE_CHANNEL)
        return value if value in {"beta", "stable"} else DEFAULT_RELEASE_CHANNEL
    except (OSError, ValueError, json.JSONDecodeError):
        return DEFAULT_RELEASE_CHANNEL


def set_selected_channel(channel: str, *, paths=None) -> None:
    if channel not in {"beta", "stable"}:
        raise ValueError("Unsupported update channel.")
    paths = paths or runtime_paths(); paths.config.mkdir(parents=True, exist_ok=True)
    destination = paths.config / "update-settings.json"; temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps({"schema_version": 1, "channel": channel}, sort_keys=True), encoding="utf-8")
    os.replace(temporary, destination)


def configured_update_client(*, paths=None, environ=None) -> UpdateClient | None:
    """Build a client only when both a release endpoint and public keys exist.

    Public keys are build/release configuration, never licence keys.  Empty
    configuration is a safe offline/no-update state, suitable before the first
    public release endpoint is approved.
    """
    environ = os.environ if environ is None else environ
    endpoint = environ.get("QUANTUM_STUDIO_UPDATE_ENDPOINT", "")
    encoded_keys = environ.get("QUANTUM_STUDIO_UPDATE_PUBLIC_KEYS", "")
    if not endpoint or not encoded_keys:
        return None
    try:
        raw = json.loads(encoded_keys)
        keys = {str(kid): b64url_decode(str(key)) for kid, key in raw.items()}
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    selected_paths = paths or runtime_paths()
    platform = platform_record()
    if platform == "unsupported":
        return None
    return UpdateClient(HttpsUpdateSource(endpoint), UpdateVerifier(keys), current_version=APP_VERSION,
                        platform=platform, channel=selected_channel(paths=selected_paths),
                        runtime_schema_version=RUNTIME_SCHEMA_VERSION, paths=selected_paths)
