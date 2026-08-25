# Calculate v0.1 verification checklist

1. Create/import a structure. 2. Select a ready calculation. 3. Choose Fast, Intermediate, Precise, or Custom and save parameters. 4. Assign explicit pseudopotentials. 5. Preview and generate inputs. 6. Configure local tools, preflight, run/cancel/retry/recover. 7. Open Results for an execution and inspect source-hashed summaries. 8. Re-parse stale raw outputs through the backend result service when parser source selection is available. 9. Confirm Builder is unchanged by Results.


C9P GUI checks: configure fields using typed controls rather than raw JSON; choose an ordered BZ-recommended band path or a structured custom path; confirm the path comes from the request snapshot; select a completed execution; parse/re-parse results; verify result rows remain scoped to that attempt and that Builder stays unchanged.  Verify long technical paths/hashes through tooltips/details rather than primary-label truncation.
