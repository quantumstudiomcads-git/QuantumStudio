"""Cross-platform deterministic fake executable fixtures."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def write_fake_executable(path: str | os.PathLike[str], body: str) -> Path:
    """Write *body* as a directly launchable fixture and return its path."""
    target = Path(path)
    if os.name == "nt":
        script = target.with_name(target.name + ".py")
        script.write_text(body, encoding="utf-8")
        wrapper = target.with_name(target.name + ".cmd")
        wrapper.write_text(f'@echo off\r\ncall "{sys.executable}" "{script}" %*\r\nexit /b %errorlevel%\r\n', encoding="utf-8")
        return wrapper
    target.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    target.chmod(target.stat().st_mode | 0o100)
    return target


def write_python_fixture(path: str | os.PathLike[str], body: str) -> Path:
    """Write a Python fixture intended to run through ``sys.executable``."""
    target = Path(path)
    target.write_text(body, encoding="utf-8")
    return target


def runtime_path(path: str | os.PathLike[str]) -> str:
    """Represent an E:-drive fixture path in the runtime's POSIX namespace."""
    resolved = Path(path).resolve()
    if os.name == "nt":
        return "/" + resolved.as_posix()
    return "/" + resolved.relative_to(Path(resolved.anchor)).as_posix()
