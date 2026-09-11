# Quantum Studio v0.2 — B2 UI Hardening Audit

## Scope and starting point

B2 started on clean `beta-hardening-v0.2` at `65e0804` with the W8.4 baseline tag preserved. This phase covers active Qt surfaces, product consistency, error/empty states, Help/About/Diagnostics, logging access, keyboard/focus basics, and Windows geometry/startup behavior. Scientific semantics, `.qs` schema, execution contracts, Builder QPainter rendering, and the 147-entry catalogue are frozen.

## UI inventory

| Surface | Audited | Changes | Remaining issues |
|---|---|---|---|
| Project Hub | Yes | Help menu, shared theme, version identity retained, recent empty/missing behavior reviewed | Physical DPI/manual visual matrix |
| Project Window | Yes | Help/About/Diagnostics, focus styling, safe geometry import fixed | Full multi-monitor physical matrix |
| Builder | Yes | No renderer/science changes; existing empty/disabled boundaries retained | Some legacy local styles remain |
| Device Builder | Yes | Existing status/scroll panels retained | Detailed spacing pass deferred |
| Calculate | Yes | Existing search/filter and 147 catalogue retained; shared theme applied globally | Runtime status could be more prominent |
| Analyze | Yes | Existing no-result/partial/stale states retained; shared theme applied globally | Dense legacy inline styles remain |
| Brillouin Zone/dialogs | Yes | Dialog/tooltips reviewed; no scientific changes | Broader dialog normalization deferred |
| Settings/preferences | No active surface found | None | No reachable settings window in current product |
| Help/About/Diagnostics | Yes | Added shared Help menu, canonical About, diagnostics export | Log-folder opener deferred |
| Menus/toolbars/context menus | Yes | Help integrated; Builder toolbar preserved | Icon treatment remains mostly text-based |

## Changes made

`frontend/app/theme.py` supplies the smallest shared token layer: graphite/panel/accent colors, compact spacing constants, control height, standard typography, focus, hover, pressed, disabled, menu, and tooltip states. It is installed at application startup without replacing workspace-specific styling.

`backend/runtime/logging_service.py` configures `RotatingFileHandler` at the canonical local logs root with a 2 MiB file limit and three backups. Handler setup is idempotent and falls back to `NullHandler` if the directory is unavailable, so logging cannot brick startup. Session headers contain only product/build/platform/runtime identity.

`frontend/app/help_actions.py` adds `About Quantum Studio` and `Export Diagnostics…` to Project Hub and Project Window. About derives product name/version/channel from `backend.runtime`; diagnostics delegates to the B1 metadata-only ZIP service. Export success is a nonblocking status-bar message; failure says project data was not modified.

## Error, empty, and status policy

- Field/configuration failures remain inline where existing validation supports it.
- Recoverable workflow failures remain in the relevant status/preview area.
- Project/file failures use concise modal messages when a decision is required.
- Empty workspaces state what is missing and the next action; Analyze and Calculate already provide explicit no-result/no-structure text.
- Raw tracebacks are not used as the primary new UI message; detailed diagnostics remain in logs where available.
- Successful saves/exports use status-bar feedback rather than modal success dialogs.

## Windows/DPI/geometry

Automated offscreen Qt tests cover widget construction, canonical labels, menus, and focus/disabled stylesheet rules. Existing Project Window off-screen recovery remains active and uses available screen geometry. A physical 100/125/150/200% DPI and monitor-removal matrix remains a manual validation requirement; no pixel-perfect PASS is claimed here.

## Privacy and offline behavior

Diagnostics reuses the B1 backend and exports only an explicit manifest. It excludes project files, atomic coordinates, scientific inputs/outputs, pseudopotential contents, licence material, tokens, and private keys. Help/About/Diagnostics require no network and no runtime/Engine Pack installation.

## Packaged validation

The required next-generation standalone bundle was built as r21 from source
commit `f530ed8` with `dirty=false`, Python 3.13.15, PySide6 6.11.2, Nuitka
4.1.1, MSVC v143, and Windows SDK 10.0.26100.0. The bundle contains 369 files
and is 485,791,401 bytes; `QuantumStudio.exe` is 293,005,824 bytes with SHA-256
`D868A51F0512AEDBBDF13FBC00621BBEF5E24809874F1949964300BCF3332F3F`. It
launched responsively from the standalone directory with no developer
environment. CUA/physical visual inspection was unavailable in this run, so
the DPI and visual checklist remains an explicit human confirmation item.

## Deferred work

- Physical DPI/multi-monitor/read-only visual matrix.
- Open Log Folder action.
- Full normalization of historical workspace-local styles.
- B3 catalogue-gap audit, including Phonon Band Structure and Phonon DOS exposure.
- B4 entitlement integration at the capability/catalogue policy boundary; no licensing checks were added.
- B5 manual authoring and screenshots.

## Current UI names for B5

Top-level surfaces are `Builder`, `Device Builder`, `Calculate`, and `Analyze`. The application starts at `Project Hub`; project windows expose `File` and `Help`, with `About Quantum Studio` and `Export Diagnostics…` under Help. The canonical product identity is `Quantum Studio 0.2.0`.
