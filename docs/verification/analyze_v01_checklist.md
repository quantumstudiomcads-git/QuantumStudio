# Analyze v0.1 manual verification checklist

Run from a normal project window after parsing representative Results in Calculate.

1. **Empty project:** open Analyze; confirm the concise “No results to analyze” message and no empty plot or inactive control clutter.
2. **Unparsed calculation:** confirm the separate message directing the user to Parse Results in Calculate.
3. **Selectors:** choose a calculation, execution, and Result; confirm readable names, correct child refresh, and no workflow-folder browsing in the normal flow.
4. **Single Result:** switch SCF, Bands, DOS, PDOS, and Phonon DOS repeatedly. Confirm old controls/curves/statuses disappear and provenance follows the selected execution.
5. **Bands:** inspect axis units, reference choices, repeated high-symmetry positions, optional VBM/CBM markers, and sampled-path terminology.
6. **Electronic Analysis:** verify readable semiconductor/metallic/unavailable wording. For an eligible fixture choose carrier, extremum, direction, and fit points; Fit, change one setting, verify the fit clears, refit, and inspect the dark Δk (Å⁻¹) preview and quality text.
7. **PDOS:** change filters and aggregation; confirm the table follows the active selection and an unmatched filter explains that no channels match.
8. **Compare:** Add compatible Results using Calculation → Execution → Result; reorder/hide one, inspect explicit difference direction and ineligibility explanations. Check derived gap table and explicit-strain trend only where metadata exists.
9. **Exports:** export CSV, PNG/SVG/PDF, comparison package, electronic JSON, and strain CSV. Confirm extensions are not duplicated and files contain expected provenance/units.
10. **Result status:** inspect STALE/PARTIAL/UNVERIFIED Result if available; warning text must remain visible. A corrupt/missing root must not prevent other Results from opening.
11. **Layout:** test 1280×720, 1366×768, 1920×1080, maximize/restore, and keyboard Escape in dialogs. Verify dark tooltips/menus and reachable primary controls.
12. **Refresh:** use Refresh Results after new Calculate Results are present; confirm valid selection is retained or replaced by a sensible fallback.

Analyze v0.1 never parses raw engine files, launches scientific tools, or modifies Builder/Calculate state. The read-only relaxed-structure viewer remains intentionally deferred until a public renderer exists.
