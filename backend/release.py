"""Canonical release identity shared by desktop packages and the updater."""
from __future__ import annotations

from dataclasses import dataclass
import re

PRODUCT_NAME = "Quantum Studio"
APP_VERSION = "0.2.0"
ENGINE_PACK_VERSION = "unbundled"
RUNTIME_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
DEFAULT_RELEASE_CHANNEL = "beta"
SUPPORTED_RELEASE_CHANNELS = frozenset({"beta", "stable"})

_VERSION = re.compile(r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<channel>beta)\.(?P<serial>0|[1-9]\d*))?$")


class ReleaseVersionError(ValueError):
    """A release version cannot participate in the signed update protocol."""


@dataclass(frozen=True, order=True)
class ReleaseVersion:
    """Strict, dependency-free ordering for stable and beta release tags."""

    major: int
    minor: int
    patch: int
    prerelease_rank: int
    serial: int

    @classmethod
    def parse(cls, value: str) -> "ReleaseVersion":
        match = _VERSION.fullmatch(str(value))
        if match is None:
            raise ReleaseVersionError("Release version must be MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-beta.N.")
        groups = match.groupdict()
        return cls(int(groups["major"]), int(groups["minor"]), int(groups["patch"]),
                   0 if groups["channel"] else 1, int(groups["serial"] or 0))

    @classmethod
    def validate_channel(cls, value: str, channel: str) -> "ReleaseVersion":
        parsed = cls.parse(value)
        if channel not in SUPPORTED_RELEASE_CHANNELS:
            raise ReleaseVersionError("Unsupported release channel.")
        if channel == "stable" and parsed.prerelease_rank == 0:
            raise ReleaseVersionError("Stable channel cannot advertise a beta version.")
        return parsed
