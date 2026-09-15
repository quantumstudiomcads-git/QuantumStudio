# B5.3 visual QA

## Scope and evidence

The accepted binary was verified before documentation work:

- Build: Quantum Studio 0.2.0 r28 standalone.
- Executable SHA-256:
  `1122712B403A6BC885EAC4CA402BEBB384F4A2F6F6D75D1A28CF8092516E1749`.
- UI source rule: current UI imagery may only come from that executable.

The available B5.3 automation surface exposed a browser only and no native
Windows application surface. Consequently, this QA pass did not claim visual
verification for a state that could not be opened and inspected honestly. The
source-grounded B5.1/B5.2 verification remains recorded separately.

| Manual section | UI verified? | r28 control/state | Screenshot | Notes |
| --- | --- | --- | --- | --- |
| First Launch / Project Hub | BLOCKED | Project Hub, New Project, Open Project, Recent Projects | Pending | Native r28 capture surface unavailable. |
| Builder | BLOCKED | Builder viewport, build controls, labels | Pending | Native r28 capture surface unavailable. |
| Structure Operations | BLOCKED | Supercell, slab, nanotube controls | Pending | Native r28 capture surface unavailable. |
| Measurements | BLOCKED | Picking and measurement controls | Pending | Native r28 capture surface unavailable. |
| Heterostructures / Moiré | BLOCKED | Layer matching and twist controls | Pending | Native r28 capture surface unavailable. |
| Device Builder | BLOCKED | Gated/denied state | Pending | No native capture surface; no Pro/Organization entitlement was fabricated. |
| Calculate / phonons | BLOCKED | Catalogue and the three phonon intents | Pending | Native r28 capture surface unavailable. |
| Results / Analyze | BLOCKED | Parsed-result and comparison views | Pending | No non-private parsed r28 result was available; no result was fabricated. |
| Export | BLOCKED | Current data/figure export state | Pending | Native r28 capture surface unavailable. |
| Licensing | BLOCKED | License Status and paid-feature denial | Pending | Native r28 capture surface unavailable. |
| Help / About / Diagnostics | BLOCKED | About and Help → Export Diagnostics | Pending | Native r28 capture surface unavailable. |

## B5.3 decision

The absence of a permitted native r28 surface is a documentation-capture
blocker, not a product failure. The manual keeps explicit pending notices rather
than using substitutes.
