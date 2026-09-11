# Beta Hardening Backlog

| ID | Severity | Area | Description | Status | Owner phase | Acceptance condition |
|---|---|---|---|---|---|---|
| BH-P0-001 | P0 | Windows execution paths | Native source-mode runtime paths needed drive-aware host mapping and trusted script validation. | Fixed | B1 | W4/W5 native Windows runtime tests pass without weakening managed Linux path trust. |
| BH-P1-001 | P1 | Project recovery | Malformed `.qs` payloads needed actionable typed refusal and Save As identity preservation. | Fixed | B1 | Corrupt fixtures fail safely; existing target remains untouched; legacy fixtures load. |
| BH-P1-002 | P1 | Recent projects | Malformed entries and recent-state writes needed tolerant filtering and atomic replacement. | Fixed | B1 | Missing/duplicate/non-path entries do not crash or leave temp state. |
| BH-P1-003 | P1 | Diagnostics | Safe metadata export backend was absent. | Fixed | B1 | ZIP contains only explicit manifest metadata and no project/scientific files. |
| BH-P2-001 | P2 | Logging | Establish rotating application log policy and attach operation/execution IDs consistently. | Partial — bounded session logging implemented; operation-ID enrichment remains | B2 UI | Logs are safe, bounded, timestamped, and linked to user-facing recovery details. |
| BH-P2-002 | P2 | Diagnostics UI | Add Help → Export Diagnostics and preview privacy exclusions. | Done | B2 UI | User can export the tested backend bundle from the GUI. |
| BH-P2-003 | P2 | Windows QA | Complete physical 125/150/200% DPI, multi-monitor, ACL/file-lock, and close-during-worker matrix. | Partial — automated geometry/startup checks; physical matrix remains | B2 UI | Native manual matrix passes without data loss or off-screen windows. |
| BH-P3-001 | P3 | Catalogue/documentation | Record unclear/future catalogue capabilities for a separate catalogue/manual pass. | Deferred | B3 Catalogue / B5 Manual | No new science is added during B1; follow-up scope is separately approved. |
