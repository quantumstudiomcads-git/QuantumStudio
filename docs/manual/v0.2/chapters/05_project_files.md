# 5. .qs Project Files

A Quantum Studio Project uses the .qs extension. The current format is UTF-8 JSON with schema identifier qstudio and schema version 0.4.

## What a project stores

The current schema stores Project metadata, canonical Structure payload, optional Device state, persisted calculation requests, and calculator/workflow/result/analysis metadata. Calculation requests retain source state needed to reproduce their configuration relationship to the Project.

## What is not embedded

.qs is not an all-in-one engine archive. It does not embed engine binaries, scientific runtime payloads, compiler caches, viewport state, histories, assembled Device previews, or complete external workflow roots. Execution roots are opaque external path references and can be host/path specific.

## Saving and compatibility

Projects are saved through a temporary UTF-8 file, synchronization, and atomic replacement. Optional Device or calculation records are independently recoverable: malformed optional data is recorded without necessarily preventing the base Project from opening.

You can copy a .qs file to a path with spaces or Unicode characters. To move a Project between machines, also preserve any external data needed by referenced workflows; portability of external roots is not guaranteed by .qs alone.

> **Warning:** A .qs file does not prove that the original external engine installation, pseudopotential cache, or output paths are present on a second machine.
