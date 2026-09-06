# B3 Distribution / Runtime Audit

- Product: Quantum Studio
- Version: 0.2.0
- Standalone package: PASS (468107183 bytes)
- Relocated/no-engine startup: PASS
- Application package excludes scientific Engine Pack binaries.
- Scientific engine launches: 0 (safe version/help probes are separate).

## Toolchain

- Build Python: <repository-root>/.venv-build/bin/python
- PySide6: 6.11.2
- Nuitka: 4.2.1
- patchelf: patchelf 0.18.0

## Runtime paths

- config: $USER_HOME/.config/QuantumStudio
- data: $USER_HOME/.local/share/QuantumStudio
- cache: $USER_HOME/.cache/QuantumStudio
- workflows: $USER_HOME/.local/share/QuantumStudio/workflows
- logs: $USER_HOME/.local/share/QuantumStudio/logs
- pseudos: $USER_HOME/.local/share/QuantumStudio/pseudopotentials
- engine_config: $USER_HOME/.config/QuantumStudio/engines

## Status

- Project Hub/source and relocated packaged startup passed in isolated runtime paths.
- No-engine and offline startup are nonblocking.
- Engine Pack manifests are versioned, relocatable, and SHA-256 checked.
- Desktop and .qs MIME metadata contain no developer absolute paths.
- Legal text remains pending review; Windows/WSL remains deferred.
