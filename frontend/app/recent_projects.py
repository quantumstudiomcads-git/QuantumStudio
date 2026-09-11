"""Recent-project persistence in the application configuration root."""
from __future__ import annotations
import json
import os
from pathlib import Path
from backend.runtime import runtime_paths

MAX_RECENT_PROJECTS = 10

def recent_file(*, environ=None, home=None, platform_name=None) -> Path:
    """Return mutable config storage; never a source/bundle-relative path."""
    return runtime_paths(environ=environ, home=home, platform_name=platform_name).config / "recent_projects.json"

def _ensure_directory(path: Path) -> None: path.parent.mkdir(parents=True, exist_ok=True)

def load_recent_projects(*, environ=None, home=None, platform_name=None):
    path=recent_file(environ=environ,home=home,platform_name=platform_name); _ensure_directory(path)
    try: data=json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    except (OSError,json.JSONDecodeError): return []
    unique=[]
    for item in data if isinstance(data,list) else []:
        candidate=Path(str(item)).expanduser()
        if candidate.exists() and candidate.suffix==".qs":
            value=str(candidate.resolve())
            if value not in unique: unique.append(value)
    return unique[:MAX_RECENT_PROJECTS]

def save_recent_projects(paths, *, environ=None, home=None, platform_name=None):
    target=recent_file(environ=environ,home=home,platform_name=platform_name); _ensure_directory(target); unique=[]
    for item in paths:
        try:
            candidate=Path(item).expanduser()
        except (TypeError, ValueError):
            continue
        if candidate.exists() and candidate.suffix==".qs":
            value=str(candidate.resolve())
            if value not in unique: unique.append(value)
    temporary=target.with_name(f".{target.name}.tmp")
    try:
        temporary.write_text(json.dumps(unique[:MAX_RECENT_PROJECTS],indent=4)+"\n",encoding="utf-8")
        os.replace(temporary,target)
    finally:
        if temporary.exists(): temporary.unlink()

def add_recent_project(path):
    path=Path(path).expanduser().resolve()
    if not path.exists() or path.suffix != ".qs": return
    save_recent_projects([str(path),*load_recent_projects()])

def remove_recent_project(path):
    value=str(Path(path).expanduser().resolve()); save_recent_projects([item for item in load_recent_projects() if item != value])

def clear_recent_projects():
    target=recent_file()
    try: target.unlink()
    except FileNotFoundError: pass
