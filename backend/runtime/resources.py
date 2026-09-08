"""Central source/frozen application resource discovery.

No mutable data belongs here.  Application data is obtained through
``runtime_paths`` and remains outside a standalone bundle.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys
from .paths import RuntimePaths, runtime_paths

class ResourceError(RuntimeError): pass

@dataclass(frozen=True)
class ApplicationResources:
    root: Path
    packaged: bool

    @classmethod
    def discover(cls, *, executable: str | Path | None = None, frozen: bool | None = None, source_root: str | Path | None = None) -> "ApplicationResources":
        packaged = bool(getattr(sys, "frozen", False) or "__compiled__" in globals()) if frozen is None else bool(frozen)
        if packaged:
            root = Path(executable or sys.argv[0]).resolve().parent
        else:
            root = Path(source_root).resolve() if source_root is not None else Path(__file__).resolve().parents[2]
        return cls(root, packaged)

    def path(self, relative: str | Path, *, required: bool = True) -> Path:
        item = Path(relative)
        if item.is_absolute() or ".." in item.parts:
            raise ResourceError("Application resource path escapes the install root.")
        target = (self.root / item).resolve()
        if target != self.root and self.root not in target.parents:
            raise ResourceError("Application resource path escapes the install root.")
        if required and not target.is_file():
            raise ResourceError(f"Required application resource is missing: {item.as_posix()}")
        return target

    @property
    def assets(self) -> Path:
        return self.path("assets", required=False)


def application_resources(**kwargs) -> ApplicationResources:
    return ApplicationResources.discover(**kwargs)


def initialize_application_data() -> RuntimePaths:
    """Create only writable application-data roots, never bundle-relative state."""
    paths = runtime_paths(); paths.ensure_user_dirs(); return paths
