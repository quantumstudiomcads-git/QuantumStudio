# 28. Files and Directories

The following are production Windows locations. They are not development paths.

| Purpose | Location |
| --- | --- |
| Configuration and recent projects | %APPDATA%\QuantumStudio |
| Recent-project record | %APPDATA%\QuantumStudio\recent_projects.json |
| Data root | %LOCALAPPDATA%\QuantumStudio |
| Logs | %LOCALAPPDATA%\QuantumStudio\logs |
| Licensing state | %LOCALAPPDATA%\QuantumStudio\licensing |
| Diagnostics | %LOCALAPPDATA%\QuantumStudio\diagnostics |
| Pseudopotential cache | %LOCALAPPDATA%\QuantumStudio\pseudopotentials |
| Workflow roots | %LOCALAPPDATA%\QuantumStudio\workflows unless configured otherwise |
| Runtime metadata | %LOCALAPPDATA%\QuantumStudio\runtime |

Licensing state is per-user and protected through the current Windows DPAPI
design. Do not copy or edit licensing blobs manually. Recent-project records
are references to .qs files, not copies of the projects themselves.

> **Privacy note:** Paths can reveal user-local information. Use a neutral
> destination when exporting diagnostics or screenshots for support.
