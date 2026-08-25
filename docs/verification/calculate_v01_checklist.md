# Calculate v0.1 verification checklist

1. Create/import a structure. 2. Select a ready calculation. 3. Choose Fast, Intermediate, Precise, or Custom and save parameters. 4. Assign explicit pseudopotentials. 5. Preview and generate inputs. 6. Configure local tools, preflight, run/cancel/retry/recover. 7. Open Results for an execution and inspect source-hashed summaries. 8. Re-parse stale raw outputs through the backend result service when parser source selection is available. 9. Confirm Builder is unchanged by Results.


C9P GUI checks: configure fields using typed controls rather than raw JSON; choose an ordered BZ-recommended band path or a structured custom path; confirm the path comes from the request snapshot; select a completed execution; parse/re-parse results; verify result rows remain scoped to that attempt and that Builder stays unchanged.  Verify long technical paths/hashes through tooltips/details rather than primary-label truncation.


C9Q provisioning checks: start an Auto PBE request with an empty managed cache; verify a compatible pseudo is provisioned and persisted with SHA/provider/version; repeat offline/cache-first; change PBE to HSE06 and confirm PBE-parent reuse; change to B3LYP/PZ/PW91 and confirm no PBE fallback; enable SOC and require FR resolution where available; verify provider/download failure leaves no final cache artifact; use Manual import and confirm it is not replaced. Confirm the footer keeps only Generate/Run/More and secondary actions remain reachable from More.


C9R runtime checks: select Local Machine and one core for direct execution; select multiple cores with a configured MPI launcher and verify preflight plus rank launch; verify missing MPI blocks only multi-rank MPI-capable tasks; set OpenMP threads and inspect the child environment; cancel a controlled local run; confirm CPU/MPI/OpenMP values are absent from the saved scientific request.
