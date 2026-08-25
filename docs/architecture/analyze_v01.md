# Analyze v0.1

Analyze is a result-only, engine-neutral workspace. It consumes `ScientificResult` metadata and arrays through `ResultStore`/`ResultService`; it never invokes scientific executables, compilers, QE writers, or raw-output parsers. Historical request/execution provenance is used instead of the mutable Builder structure.

A1 provides calculation/execution/result selectors, Overview, provenance, bounded data tables, CSV/image export, and dark-theme Matplotlib views for band, DOS, PDOS-compatible, and phonon-DOS-compatible arrays. Results retain status (including STALE, PARTIAL, and UNVERIFIED). A workflow-root attachment is required because C7 execution roots are currently selected by Calculate rather than indexed at project level.

The plotting boundary is `ScientificPlotWidget`; engine-specific views consume result types only. Future comparison is intentionally architectural only. Analyze does not parse, re-run, compile, generate, or mutate project structures.
