"""Privacy-safe beta diagnostics metadata and deterministic export."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import zipfile

from .identity import BUILD_CHANNEL, PRODUCT_NAME, VERSION, build_identity
from .paths import runtime_paths

DIAGNOSTICS_SCHEMA_VERSION = "1"


def collect_diagnostics(*, environ=None, home=None, platform_name=None) -> dict:
    paths = runtime_paths(environ=environ, home=home, platform_name=platform_name)
    return {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "product": {"name": PRODUCT_NAME, "version": VERSION, "build_channel": BUILD_CHANNEL, "identity": build_identity()},
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "python": sys.version.split()[0]},
        "qt": _qt_identity(),
        "paths": {"config": str(paths.config), "data": str(paths.data), "cache": str(paths.cache), "logs": str(paths.logs), "workflows": str(paths.workflows), "pseudos": str(paths.pseudos)},
        "runtime": {"status": "not_probed", "engine_pack_status": "not_probed", "wsl_status": "not_probed"},
    }


def _qt_identity() -> dict[str, str]:
    try:
        from PySide6 import __version__
        return {"pyside6": str(__version__)}
    except Exception:
        return {"pyside6": "unavailable"}


def export_diagnostics(destination, *, environ=None, home=None, platform_name=None) -> Path:
    """Write a metadata-only ZIP; project and scientific files are never collected."""
    target = Path(destination)
    if target.suffix.lower() != ".zip":
        target = target.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = collect_diagnostics(environ=environ, home=home, platform_name=platform_name)
    manifest["exported_at"] = datetime.now(timezone.utc).isoformat()
    encoded = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            info = zipfile.ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, encoded)
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target
