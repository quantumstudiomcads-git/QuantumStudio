# 26. Diagnostics

Use **Help → Export Diagnostics…** to create a support-oriented, metadata-only
diagnostic archive. The application also provides **About Quantum Studio** and
**License Status** in Help.

## Logs

On Windows, Quantum Studio writes a rotating log at:

    %LOCALAPPDATA%\QuantumStudio\logs\quantumstudio.log

The configured rotation is 2 MiB with three backups. Logging is best-effort:
failure to create a log root must not prevent basic GUI startup.

## Diagnostic privacy

Diagnostics are designed to contain safe metadata such as product/platform/Qt
information, selected safe runtime status, and safe licensing status fields.
They intentionally exclude project/scientific files, raw signed leases, private
device keys, authentication tokens, billing data, and signing material.

> **Screenshot pending:** A native r28 window-capture surface was unavailable during B5.3; no substitute image was used.

> **Warning:** A diagnostics archive is not a reproducibility archive. Export
> the relevant supported result data separately when that is required.
