# Analyze v0.1

Analyze is a result-only, engine-neutral workspace. It consumes `ScientificResult` metadata and arrays through `ResultStore`/`ResultService`; it never invokes scientific executables, compilers, QE writers, or raw-output parsers. Historical request/execution provenance is used instead of the mutable Builder structure.

A1 provides calculation/execution/result selectors, Overview, provenance, bounded data tables, CSV/image export, and dark-theme Matplotlib views for band, DOS, PDOS-compatible, and phonon-DOS-compatible arrays. Results retain status (including STALE, PARTIAL, and UNVERIFIED). A workflow-root attachment is required because C7 execution roots are currently selected by Calculate rather than indexed at project level.

The plotting boundary is `ScientificPlotWidget`; engine-specific views consume result types only. Future comparison is intentionally architectural only. Analyze does not parse, re-run, compile, generate, or mutate project structures.

## A3 comparison

`AnalysisSeries` references one `ScientificResult` with request/execution/provenance metadata; `ComparisonModel` validates result-family, units/path topology, and status compatibility before plotting. Compare Results is session-only and never changes Project or ResultStore. Band paths must match topology; different sampling uses each series' own coordinate and is not silently interpolated. DOS/PDOS/phonon-DOS overlays retain physical values and units. Scalar Results are suitable for summary tables, not curve overlays. Stale and unverified series remain visibly marked. Comparison exports use structured Result data and future comparison-series persistence/interpolation is deferred.

## A4 comparison completion

Compare Results uses a metadata-first Calculation → Execution → Result picker. `AnalysisSeries` remain session-only and can be reordered, renamed, hidden, or removed without mutating Project/ResultStore. Shared energy alignment is a Qt-free transform; Fermi/VBM references require metadata on every visible series. Exact differences require identical axes/shapes and never interpolate. Frequency conversion is limited to explicit THz↔cm^-1 conversion. Comparison provenance and per-series CSV/metadata export remain structured; total-energy differences across differing functionals/pseudopotentials are not automatically interpreted.

## A5 comparison UI

A5 exposes dependent Calculation → Execution → Result picking, session-only series labels/order/visibility, shared energy-reference and range controls, explicit `Difference B - A` mode, and comparison export packages (`comparison.json` plus per-series CSV). Difference mode uses only exact backend transforms with compatible axes/shapes; no interpolation is performed. Status warnings and subtraction direction remain visible. Total-energy interpretation across differing Hamiltonians remains prohibited.

## A6 derived electronic analysis

Band-edge analysis consumes only structured BandStructureResult data and defensible occupation metadata. It returns typed VBM/CBM/gap objects with `sampled_path`, `full_bz`, or `unknown` scope; path extrema are never called fundamental without full-BZ provenance. Directness uses physical k-point equivalence, including repeated reciprocal points. Effective mass uses physical reciprocal distance and local quadratic fits with sample count, curvature, R², range, direction, and quality warnings. Original ScientificResult arrays are immutable; unresolved occupancy, crossings, insufficient samples, and invalid cells return unavailable diagnostics.


## A7 interactive electronic analysis

A7 renders A6-derived VBM/CBM candidates as optional band-plot markers while preserving every displayed occurrence of degenerate or repeated high-symmetry points. `VBM = 0` is offered only after a valid derived VBM is available; it is a non-mutating display offset, as is Fermi alignment. The Electronic Analysis panel reports source status separately from derived status and keeps sampled-path terminology unless `gap_scope == full_bz`.

Effective mass remains a user-reviewed local fit. The user selects CBM/VBM, a retained edge candidate, one continuous sampled reciprocal-space direction, and a bounded point count. The Qt-free backend returns curvature, conventional positive electron/hole mass, R², physical Δk range, fit samples, fitted values, one-sided status, and warnings; the UI only displays those data in a secondary fit preview. It never fits across a path corner, changes band branch, or uses plotting coordinates.

Compare mode can display a derived electronic table and `B - A` sampled-gap delta only when both edges are valid and have the same scope. Metallic and unresolved series remain visible but have no gap delta. Gap-vs-strain trends accept only explicit numeric strain metadata, sort it numerically, retain provenance in CSV export, reject mixed scopes, and do not interpolate or predict a trend. Derived JSON exports contain scalar analysis/provenance/fit diagnostics, never large raw band arrays.

A read-only final-structure preview remains deferred: Analyze has no clean public structure-renderer boundary at this stage, and it must not import Builder private controllers or mutate Project.structure.


## A8 polish and feature freeze

A8 completes Analyze v0.1 usability and QA without adding scientific analysis. The workspace distinguishes empty projects, unparsed calculations, unavailable result roots, and per-result errors; Result refresh remains metadata-first. The Data tab now uses a lightweight Qt model/view rather than allocating item widgets for every numeric cell, and replaced Matplotlib canvases clear their figures before deferred deletion. Exports normalize missing extensions and show contextual failures.

Analyze v0.1 feature set is **frozen after A8**. Post-freeze work is limited to defect fixes, scientific-correctness fixes, performance, accessibility/usability work, and release blockers. Deferred scope includes a public read-only relaxed-structure renderer, volumetric fields, transport/optics without structured Results, full-BZ extrema/gap search, advanced interpolation, and persisted comparison sessions.

## Band presentation

Band Structure Results remain immutable structured data. Analyze offers a Publication display mode with persisted high-symmetry labels/separators, validated VBM/CBM markers, sampled-path and minimum-direct-gap summaries, and session-only annotations. Overlay uses the existing comparison model and requires compatible path topology. Publication styling and measurements never alter scientific Results or provenance; conventional/supercell folding remains a scope warning rather than an automatic primitive-cell transform.

## Publication band figure

The BandPlot defaults to a boxed Publication presentation: white canvas, dark bands, inward ticks, categorical persisted high-symmetry labels, subtle separators, and general grid disabled. The Grid checkbox controls only ordinary Matplotlib grid artists; separators and energy-reference guides are independent. Appearance controls and point readout are session-only and re-style immutable Results.
