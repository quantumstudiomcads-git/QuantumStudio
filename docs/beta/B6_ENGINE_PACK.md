# B6 Engine Pack

The scientific payload is a separately versioned immutable Linux/x86_64 Engine
Pack.  It is intended to be shared by native Linux and Windows through
`QuantumStudioRuntime` only when ABI and runtime compatibility are validated.
The desktop application version, runtime schema, manifest schema, and Engine
Pack version are independent.

Existing W5 code installs a verified pack under a versioned `packs/` directory,
validates `engine-pack.json` and each declared binary SHA-256, then atomically
replaces `active.json`.  It retains the prior pack and rejects silent downgrade
or unowned roots.  The runtime agent maps logical tool IDs to declared absolute
paths and never searches ambient `PATH`.

No third-party scientific binary is newly bundled by B6.  Packaging Quantum
ESPRESSO, Wannier90, EPW, and BoltzTraP2 remains **BLOCKED pending legal
review**.  A proposed pack must first record each component's version, licence,
source URL, licence text, notice/source-distribution obligations, binary
redistribution status, and approval.  The release pipeline may advertise an
Engine Pack only after such an approved artifact is available.

Engine Pack health is the existing managed-runtime boundary: registered WSL2,
verified runtime metadata, compatible runtime-agent protocol, readable pack
manifest, declared executable hashes, and agent capability check.  It does not
claim that a package is scientifically ready merely because a distro imports.
