"""Versioned, relocatable Engine Pack manifest and integrity validation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys


class EnginePackError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest for a local artifact.

    Runtime image provisioning shares this deliberately small integrity
    primitive; it does not share Engine Pack semantics.
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# Compatibility for the existing local implementation.
_sha256 = sha256_file


@dataclass(frozen=True)
class EnginePackManifest:
    schema_version: str
    engine_pack_version: str
    platform: str
    architecture: str
    engines: tuple[dict, ...]
    licenses: tuple[dict, ...] = ()

    @classmethod
    def load(cls, path: str | Path) -> "EnginePackManifest":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != "1":
            raise EnginePackError("Unsupported or malformed Engine Pack manifest schema.")
        return cls(str(data["schema_version"]), str(data["engine_pack_version"]), str(data["platform"]),
                   str(data["architecture"]), tuple(data.get("engines", ())), tuple(data.get("licenses", ())))


@dataclass(frozen=True)
class EnginePackValidation:
    valid: bool
    platform_compatible: bool
    missing: tuple[str, ...]
    mismatched: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_engine_pack(root: str | Path, *, platform_name=None, architecture=None) -> EnginePackValidation:
    root = Path(root).expanduser().resolve()
    try:
        manifest = EnginePackManifest.load(root / "engine-pack.json")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, EnginePackError) as error:
        return EnginePackValidation(False, False, (), (), (str(error),))
    platform_name = platform_name or sys.platform
    architecture = architecture or ("x86_64" if sys.maxsize > 2**32 else "x86")
    compatible = manifest.platform in {platform_name, "any"} and manifest.architecture in {architecture, "any"}
    missing, mismatched = [], []
    for item in manifest.engines:
        relative = str(item.get("relative_path", ""))
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            missing.append(str(item.get("executable", relative)))
            continue
        expected = str(item.get("sha256", ""))
        if expected and _sha256(path) != expected:
            mismatched.append(str(item.get("executable", relative)))
    warnings = ("INCOMPATIBLE_PLATFORM",) if not compatible else ()
    return EnginePackValidation(not missing and not mismatched and compatible, compatible, tuple(missing), tuple(mismatched), warnings)
