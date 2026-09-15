# B5.1 Screenshot Plan

No screenshots are captured in B5.1. Each B5.3 capture must be checked against
the accepted r28 package or the current documented UI state immediately before
publication.

| Chapter | Screen/dialog | Exact state and example | Required visible controls/callouts | Capture readiness |
| --- | --- | --- | --- | --- |
| 3–4 | Project Hub | No project open; populated recent list if safe fixture exists | New Project, Open Project, Recent Projects, Clear, footer version | r28 capable |
| 4 | New Project | Empty name then valid name/location fixture | Project name, Location, Browse, `.qs` note | r28 capable |
| 5 | Project open/recovery | Harmless example `.qs`; no personal paths | project name, save status if visible | r28 capable |
| 6 | Builder overview | Small periodic silicon or graphene fixture | navigation, viewport, Builder controls | r28 capable |
| 6 | Structure import | Import dialog with a non-sensitive fixture | accepted format/filter and confirmation | verify at capture |
| 7 | Structure operations | One operation per focused capture: supercell, slab, nanotube | inputs, validation message, result preview | verify at capture |
| 8 | Measurement | Selected atoms on a simple fixture | picking state, measurement result, clear control | verify at capture |
| 9 | Heterostructure | Two small compatible layers | layer inputs, matching/strain/gap controls, diagnostics | verify at capture |
| 10 | Moiré | Small bilayer with documented twist | twist input, matching result, size warning | verify at capture |
| 11 | Device Builder, entitled | Pro/Organization test entitlement only; no real lease | regions, properties, placement, interface controls, viewport | source-test or controlled r28 capture |
| 11/24 | Device Builder denied | No entitlement | denial title and remediation only | r28 capable |
| 12 | Calculate overview | Valid periodic fixture, no job running | category filter, calculation list/count, configured requests, action bar | r28 capable |
| 12 | Calculation configuration | One implemented SCF request | Configure, typed parameters, XC/pseudo action | r28 capable |
| 13 | Band path | Band request with valid structure | Choose Band Path, recommended/reset state | verify at capture |
| 15 | Γ phonons | `phonons` selection | exact name and status | r28 capable |
| 15 | Phonon DOS | `phonon_dos` selection | exact name and status; distinguish from dispersion | r28 capable |
| 15 | Phonon band structure | `phonon_band_structure` selection | exact name and explicit path control | r28 capable |
| 18 | XC and Pseudopotentials | Safe fixture with species assignment | Import UPF, provider status, recommended cutoffs | verify network-independent state |
| 19 | Local Tools | No scientific engine execution required | detected/missing QE status, rescan/choose controls | r28 capable |
| 20 | Job state | A controlled completed/failed fixture | workflow status and safe result relation | verify fixture |
| 21 | Results dialog | Parsed fixture result | Parse/Re-parse, result status/provenance | verify fixture |
| 22 | Analyze overview | Parsed public result fixture | result browser, plot/table/provenance, Data/Style/Details/Export | verify fixture |
| 22 | Analyze comparison | Two compatible public results | Add Result, comparison controls, reference selection, export | verify fixture |
| 23 | Export | Save dialogs with non-sensitive destination | data/figure/comparison export labels and type | verify at capture |
| 24 | License Status | No entitlement or controlled test status | safe status, plan, expiry; no token | r28 capable |
| 26 | Help and About | Main window open | About Quantum Studio, Export Diagnostics…, License Status | r28 capable |
| 26 | Diagnostics export | Save dialog then inspect metadata-only fixture archive | ZIP destination and privacy wording | r28 capable |

## Capture controls

- Use only synthetic/public example structures and paths.
- Never capture private keys, leases, account identifiers, tokens, billing data,
  local user names, or personal project paths.
- Label entitlement-gated images as controlled demonstration states.
- Do not use a screenshot to imply that a planned calculation, installer,
  engine pack, QuantumStudioRuntime, or server workflow currently ships.
- Use callouts sparingly: numbered actions, the selected calculation/status,
  and one warning where it prevents a common misunderstanding.
