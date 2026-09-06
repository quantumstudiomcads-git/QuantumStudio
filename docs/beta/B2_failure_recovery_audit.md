# B2 Failure / Recovery Audit

No scientific engine was launched in B2.

| Scenario | Expected state | Recovery action | Retryable | Status |
|---|---|---|---:|---|
| missing_executable | FAILED | CONFIGURE_ENGINE | False | TESTED_CONTRACT |
| non_executable | FAILED | CONFIGURE_ENGINE | False | TESTED_CONTRACT |
| nonzero_exit | FAILED | RETRY | True | TESTED_CONTRACT |
| signal_termination | FAILED | RETRY_OR_CHANGE_RESOURCES | True | TESTED_CONTRACT |
| user_cancellation | CANCELLED | RUN_AGAIN | False | TESTED_CONTRACT |
| stale_running_after_restart | INTERRUPTED | RETRY | True | TESTED_CONTRACT |
| required_artifact_missing_rc0 | FAILED | REPAIR_OR_RETRY | False | TESTED_CONTRACT |
| parser_failure_after_completed | COMPLETED | REPARSE | False | TESTED_CONTRACT |
| artifact_sha_mismatch | BLOCKED | REBUILD_ARTIFACT | False | TESTED_CONTRACT |
| missing_reused_artifact | BLOCKED | RECREATE_PREREQUISITE | False | TESTED_CONTRACT |
| preparation_failure | BLOCKED | EDIT_CONFIGURATION | False | TESTED_CONTRACT |
| retry_exhaustion | FAILED | EDIT_CONFIGURATION_OR_RESOURCES | False | TESTED_CONTRACT |
| disk_preflight | BLOCKED | FREE_DISK_OR_RELOCATE | False | TESTED_CONTRACT |
| process_start_failure | FAILED | CONFIGURE_ENGINE | False | TESTED_CONTRACT |
| malformed_execution_json | RECOVERY_ERROR | RESTORE_OR_REPAIR_SIDECAR | False | TESTED_CONTRACT |

## Product decisions

- Public catalogue count is 147.
- Extinction Coefficient remains in the shared Optical Properties result bundle and is not a separate public catalogue slot.
- Scientific engines launched: 0.
- B2 uses deterministic Python subprocess fixtures only.
