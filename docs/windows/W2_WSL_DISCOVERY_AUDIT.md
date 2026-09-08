# W2 WSL Discovery Audit

## Scope

W2 implements read-only, Qt-free discovery of the Windows host WSL capability,
registered distributions, and the exact managed identity `QuantumStudioRuntime`.
It does not install, import, unregister, start, repair, or modify WSL or
Windows state.

## Commands and safety

The injectable `WSLCommandRunner` resolves `wsl.exe` through normal executable
lookup and invokes only `wsl.exe --list --verbose` as the required enumeration
probe and `wsl.exe --version` as optional enrichment. Calls use structured argv,
`shell=False`, captured output, and a default three-second timeout. No distro
command is executed. Optional probe failure does not invalidate a successful
distribution table.

Output uses controlled UTF-8/UTF-16/system-code-page fallback. The parser
handles CRLF, the default `*` marker, whitespace-separated state/version
columns, names containing spaces, and Unicode names. Malformed rows produce
explicit diagnostics and never select arbitrary text as a managed runtime.

## Classification

The report separates host state, command availability, WSL2 evidence,
registered distributions, and managed-runtime health. The exact
case-insensitive managed identity is `QuantumStudioRuntime`; substring-like
names are not selected.

An exact managed distro at WSL1 is `REGISTERED_WSL1`. At WSL2 it is
`REGISTERED_WSL2`, intentionally not `READY`: W2 does not inspect its
filesystem or verify scientific tools. Random Ubuntu, Debian, or other user
distributions are never adopted.

Non-Windows hosts return `NON_WINDOWS` without invoking a subprocess. Missing
executables, timeouts, nonzero returns, and malformed output are represented by
typed report state/error fields rather than uncontrolled subprocess exceptions.

## Persistence and future work

Discovery reports are diagnostics only and are not persisted into `.qs`
scientific intent. W3 owns deterministic managed-runtime provisioning,
versioned runtime metadata, integrity verification, and idempotent
install/repair decisions. Host/runtime path translation and scientific WSL
execution remain deferred.

## Validation

W2 tests run on Linux with injected command-runner fixtures. No Windows host,
WSL installation, network, VM, or scientific engine is required. A real Windows
host probe remains a later validation requirement.
