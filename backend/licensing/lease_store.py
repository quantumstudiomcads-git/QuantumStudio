"""Contained atomic persistence for signed public lease envelopes and clock state."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from backend.runtime.paths import RuntimePaths, runtime_paths


class LeaseStoreError(ValueError):
    pass


class LeaseStore:
    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or runtime_paths()

    @property
    def root(self) -> Path:
        return self.paths.data / "licensing"

    @property
    def lease_path(self) -> Path:
        return self.root / "device-lease.json"

    @property
    def clock_path(self) -> Path:
        return self.root / "trusted-clock.json"

    def save_lease(self, envelope: Mapping[str, Any]) -> None:
        self._atomic_write(self.lease_path, envelope)

    def load_lease(self) -> dict[str, Any] | None:
        return self._load(self.lease_path)

    def save_last_trusted_time(self, timestamp: int) -> None:
        if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp <= 0:
            raise LeaseStoreError("Trusted time must be a positive integer.")
        self._atomic_write(self.clock_path, {"schema_version": 1, "last_trusted_time": timestamp})

    def load_last_trusted_time(self) -> int | None:
        payload = self._load(self.clock_path)
        if payload is None:
            return None
        value = payload.get("last_trusted_time")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise LeaseStoreError("Trusted clock metadata is invalid.")
        return value

    @staticmethod
    def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name("." + path.name + ".tmp")
        encoded = (json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        try:
            with temporary.open("wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _load(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise LeaseStoreError("Cached licence data is unreadable.") from error
        if not isinstance(payload, dict):
            raise LeaseStoreError("Cached licence data is invalid.")
        return payload
