# Windows Build — W6

W6 defines a native Windows **Nuitka standalone** bundle. It is not an installer and does not install WSL, import `QuantumStudioRuntime`, install an Engine Pack, request elevation, modify the registry, create shortcuts, or associate `.qs` files. Those are W7 responsibilities.

## Build machine

The initial target is Windows 11 x64. Build with the repository-supported Python 3.13 and PySide6 6.11.2 runtime requirements plus the build-only `requirements-build-windows.txt` dependency. The project currently records Nuitka 4.1.1 in its PySide deployment configuration. A real build requires Visual Studio 2022 Build Tools with the MSVC v143 x64/x86 tools and a Windows SDK; the build plan explicitly requests Nuitka's `--msvc=latest` backend and does not fall back to Zig or MinGW. It also caps Nuitka at four C compiler jobs and uses MSVC's supported `_CL_` appended `/Od` option: this avoids optimizer heap exhaustion in generated scientific extension modules without changing application or scientific behavior. End users do not install Python, Nuitka, or compiler tooling.

From a clean checkout on Windows:

```text
python scripts/build_windows.py --output dist/windows/QuantumStudio-0.2.0-beta --channel beta
```

`--dry-run` produces a structured plan and is the only supported mode on a non-Windows host. A real build refuses non-Windows hosts, unsupported architectures, dirty beta/release trees, unsafe existing output, missing Nuitka/PySide6, failed icon generation, failed Nuitka, or a failed package audit. Commands are structured argv with `shell=False`.

The build derives a temporary ICO from canonical `assets/quantum-studio-v0.1.svg`, packages `frontend/main.py` as `QuantumStudio.exe`, includes PySide6 via Nuitka’s plugin plus the required application/runtime packages, and places assets inside the bundle. The normal release/beta console mode is disabled. The QPainter renderer remains unchanged.

## Bundle policy

The bundle is read-only at runtime. Resources resolve from the source root during development and from the executable’s bundle root when frozen; they never rely on CWD. Mutable config/recent projects use `%APPDATA%\QuantumStudio`; logs, diagnostics, workflows, runtime import data and pseudo caches use `%LOCALAPPDATA%\QuantumStudio`.

The package audit rejects tests, Git metadata, virtual environments, rootfs/VHDX files, and scientific executable names. It does not bundle an Engine Pack or production rootfs. It writes a build manifest and a W7 installer-input manifest with explicit pending runtime-image, Engine Pack, notices, and legal-review slots.

## Real Windows validation — pending

On a Windows 11 x64 machine: build at a committed W6 revision; inspect the manifest; launch `QuantumStudio.exe` without Python/PYTHONPATH and offline; test Project Hub, Builder, Calculate with no runtime, Analyze, `.qs` save/reopen; relocate the bundle to a Unicode/space path; then test a read-only bundle root and read-only runtime health probe. Code signing is **PENDING**. Real QE validation is W8, and public Engine Pack distribution/legal review is **PENDING**.
