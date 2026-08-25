# Analyze v0.1

Analyze is a result-only, engine-neutral workspace. It consumes `ScientificResult` metadata and arrays through `ResultStore`/`ResultService`; it never invokes scientific executables, compilers, QE writers, or raw-output parsers. Historical request/execution provenance is used instead of the mutable Builder structure.

A1 provides calculation/execution/result selectors, Overview, provenance, bounded data tables, CSV/image export, and dark-theme Matplotlib views for band, DOS, PDOS-compatible, and phonon-DOS-compatible arrays. Results retain status (including STALE, PARTIAL, and UNVERIFIED). A workflow-root attachment is required because C7 execution roots are currently selected by Calculate rather than indexed at project level.

The plotting boundary is `ScientificPlotWidget`; engine-specific views consume result types only. Future comparison is intentionally architectural only. Analyze does not parse, re-run, compile, generate, or mutate project structures.

## A3 comparison

`AnalysisSeries` references one `ScientificResult` with request/execution/provenance metadata; `ComparisonModel` validates result-family, units/path topology, and status compatibility before plotting. Compare Results is session-only and never changes Project or ResultStore. Band paths must match topology; different sampling uses each series' own coordinate and is not silently interpolated. DOS/PDOS/phonon-DOS overlays retain physical values and units. Scalar Results are suitable for summary tables, not curve overlays. Stale and unverified series remain visibly marked. Comparison exports use structured Result data and future comparison-series persistence/interpolation is deferred.

## A4 comparison completion

Compare Results uses a metadata-first Calculation → Execution → Result picker. `AnalysisSeries` remain session-only and can be reordered, renamed, hidden, or removed without mutating Project/ResultStore. Shared energy alignment is a Qt-free transform; Fermi/VBM references require metadata on every visible series. Exact differences require identical axes/shapes and never interpolate. Frequency conversion is limited to explicit THz↔cm^-1 conversion. Comparison provenance and per-series CSV/metadata export remain structured; total-energy differences across differing functionals/pseudopotentials are not automatically interpreted.
