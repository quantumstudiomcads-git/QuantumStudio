# 22. Analyze

**Analyze** operates on Quantum Studio parsed Results. Its empty state directs
you to run and parse a calculation in Calculate first; it is not a generic raw
Quantum ESPRESSO output viewer.

## Current capabilities

- Result browser
- Scientific plots and tables
- Provenance/details inspection
- Appearance and styling controls
- Data and figure export
- Compatible-result comparison

The comparison workflow provides controls such as **Add Result**, **Remove**,
move/rename actions, comparison details, and available electronic-analysis
views. Compare only Results that the workspace identifies as compatible.

> **Screenshot planned for B5.3:** Analyze result browser with plot, table,
> provenance, Data, Style, Details, and Export areas.

> **Screenshot planned for B5.3:** Compatible-result comparison with reference
> selection and export controls.

Result status remains visible context: comparison or plotting does not convert
PARTIAL, NOT_CONVERGED, UNVERIFIED, PARSE_FAILED, or STALE data into VALID data.
