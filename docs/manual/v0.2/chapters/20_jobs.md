# 20. Jobs

A Job/execution is a stored workflow attempt. Task states are:

| State | User meaning |
| --- | --- |
| PENDING | Created but not ready to begin. |
| READY | Validated and prepared for execution. |
| RUNNING | An engine/task is active. |
| COMPLETED | The task process completed; inspect parsing and Result status separately. |
| FAILED | The task did not finish successfully. |
| CANCELLED | The user or workflow cancelled the task. |
| BLOCKED | A validation, dependency, entitlement, or environment condition prevents execution. |
| INTERRUPTED | Execution stopped unexpectedly or before normal completion. |

Workflow state is separately PENDING, RUNNING, COMPLETED, FAILED, or CANCELLED.

    PENDING → READY → RUNNING → COMPLETED
                     ↘ FAILED / CANCELLED / INTERRUPTED
    BLOCKED is entered when a required condition is not satisfied.

Use Calculate to inspect configured requests, compiled workflow information,
generated inputs, last output, and results. A COMPLETED task may still have a
NOT_CONVERGED, PARSE_FAILED, PARTIAL, or other non-valid Result status.
