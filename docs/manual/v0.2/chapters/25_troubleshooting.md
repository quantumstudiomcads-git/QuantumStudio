# 25. Troubleshooting

Use controlled messages and safe diagnostics rather than editing protected
application state or secrets.

| Symptom | Likely cause | Safe next action |
| --- | --- | --- |
| Application does not start | Incomplete bundle, runtime/bootstrap failure, or local environment issue | Start from the complete standalone bundle; export diagnostics if the UI opens. |
| Project will not open | Missing/corrupt .qs file or inaccessible path | Confirm the selected .qs path; preserve a copy before recovery attempts. |
| Structure is not visible | View/selection state or invalid imported geometry | Reset the current Builder view/selection and inspect cell/species. |
| Import fails | Unsupported or malformed external structure input | Check the format presented by the import dialog and validate the source file. |
| Calculation is unavailable or blocked | Planned/partial state, missing dependency, entitlement, pseudopotential, or engine | Check the calculation reference, prerequisite, status, and Local Tools. |
| Pseudopotential is missing | No compatible cached/imported UPF | Use Configure XC & Pseudopotentials and correct species/functional assignment. |
| External engine unavailable | Engine is not bundled or not discovered | Use Calculate local-tool discovery/configuration; do not assume an installer supplied it. |
| Job failed | Input, external-engine, filesystem, or runtime failure | Inspect generated inputs/last output and Result details where available. |
| Job completed but result is invalid | Parser, convergence, or scientific-status issue | Review Result status and provenance; do not treat completion as validation. |
| NOT_CONVERGED | Numerical criterion not reached | Review convergence settings and scientific model before rerunning. |
| PARSE_FAILED | Output did not match the parser contract | Preserve output/provenance and export diagnostics. |
| STALE | Source fingerprints changed after storage | Rebuild/re-run or keep the result clearly labelled as stale. |
| Licensing denied | No valid local entitlement for requested capability | Use Help → License Status; reading projects/results remains permitted where policy allows. |
| Device Builder denied | Current plan lacks workspace:device_builder | Use a valid Pro or Organization entitlement; do not expect a UI workaround. |
| Diagnostics export fails | Destination is unwritable or unavailable | Choose a writable user location and verify no false success is reported. |

When seeking support, export diagnostics through **Help → Export Diagnostics…**
and describe the action, calculation intent, Result status, and safe error code.
Do not send private keys, raw leases, or authentication material.
