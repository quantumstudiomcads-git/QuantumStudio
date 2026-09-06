"""Centralized, user-writable paths for source and packaged runtimes."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys


def _root(env_name: str, xdg_name: str, fallback: Path, environ: dict[str, str]) -> Path:
    value = environ.get(env_name) or environ.get(xdg_name)
    return Path(value).expanduser() if value else fallback


@dataclass(frozen=True)
class RuntimePaths:
    config: Path
    data: Path
    cache: Path
    workflows: Path
    logs: Path
    pseudos: Path
    engine_config: Path

    @property
    def runtime(self) -> Path:
        """Mutable runtime metadata/staging root, never the installation directory."""
        return self.data / "runtime"

    @property
    def diagnostics(self) -> Path:
        return self.data / "diagnostics"

    def ensure_user_dirs(self) -> None:
        for path in (self.config, self.data, self.cache, self.workflows, self.logs, self.pseudos, self.engine_config, self.runtime, self.diagnostics):
            path.mkdir(parents=True, exist_ok=True)


def runtime_paths(*, environ=None, home=None, platform_name=None) -> RuntimePaths:
    environ = dict(os.environ if environ is None else environ)
    home = Path(home or Path.home()).expanduser()
    platform_name = platform_name or sys.platform
    if platform_name.startswith("win"):
        config_base = Path(environ.get("APPDATA", home / "AppData" / "Roaming"))
        data_base = Path(environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        cache_base = data_base
    elif platform_name == "darwin":
        config_base = home / "Library" / "Preferences"
        data_base = home / "Library" / "Application Support"
        cache_base = home / "Library" / "Caches"
    else:
        config_base = Path(environ.get("XDG_CONFIG_HOME", home / ".config"))
        data_base = Path(environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        cache_base = Path(environ.get("XDG_CACHE_HOME", home / ".cache"))
    app_config = _root("QUANTUM_STUDIO_CONFIG_ROOT", "", config_base / "QuantumStudio", environ)
    app_data = _root("QUANTUM_STUDIO_DATA_ROOT", "", data_base / "QuantumStudio", environ)
    default_cache = (data_base / "QuantumStudio" / "cache") if platform_name.startswith("win") else (cache_base / "QuantumStudio")
    app_cache = _root("QUANTUM_STUDIO_CACHE_ROOT", "", default_cache, environ)
    workflow = Path(environ.get("QUANTUM_STUDIO_WORKFLOW_ROOT", app_data / "workflows")).expanduser()
    pseudo = Path(environ.get("QUANTUM_STUDIO_PSEUDO_CACHE", app_data / "pseudopotentials")).expanduser()
    return RuntimePaths(app_config, app_data, app_cache, workflow, app_data / "logs", pseudo, app_config / "engines")
