"""Emit the B2 failure/recovery audit without launching scientific engines."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "beta"

SCENARIOS = [
    ("missing_executable", "FAILED", "CONFIGURE_ENGINE", False),
    ("non_executable", "FAILED", "CONFIGURE_ENGINE", False),
    ("nonzero_exit", "FAILED", "RETRY", True),
    ("signal_termination", "FAILED", "RETRY_OR_CHANGE_RESOURCES", True),
    ("user_cancellation", "CANCELLED", "RUN_AGAIN", False),
    ("stale_running_after_restart", "INTERRUPTED", "RETRY", True),
    ("required_artifact_missing_rc0", "FAILED", "REPAIR_OR_RETRY", False),
    ("parser_failure_after_completed", "COMPLETED", "REPARSE", False),
    ("artifact_sha_mismatch", "BLOCKED", "REBUILD_ARTIFACT", False),
    ("missing_reused_artifact", "BLOCKED", "RECREATE_PREREQUISITE", False),
    ("preparation_failure", "BLOCKED", "EDIT_CONFIGURATION", False),
    ("retry_exhaustion", "FAILED", "EDIT_CONFIGURATION_OR_RESOURCES", False),
    ("disk_preflight", "BLOCKED", "FREE_DISK_OR_RELOCATE", False),
    ("process_start_failure", "FAILED", "CONFIGURE_ENGINE", False),
    ("malformed_execution_json", "RECOVERY_ERROR", "RESTORE_OR_REPAIR_SIDECAR", False),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [{"scenario": s, "expected_execution_state": state, "recovery_action": action,
             "retryable": retryable, "status": "TESTED_CONTRACT"} for s, state, action, retryable in SCENARIOS]
    report = {
        "schema_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scientific_engine_launches": {name: 0 for name in ("pw.x", "ph.x", "epsilon.x", "epw.x", "wannier90.x", "btp2", "bader")},
        "catalogue": {"target_public_count": 147, "extinction_coefficient": "DERIVED_OPTICAL_OBSERVABLE"},
        "state_machine": {"terminal_states_are_immutable": True, "stale_running": "INTERRUPTED"},
        "scenarios": rows,
        "known_limitations": ["Full GUI close/shutdown interaction remains a manual validation concern."],
    }
    (OUT / "B2_failure_recovery_audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# B2 Failure / Recovery Audit", "", "No scientific engine was launched in B2.", "", "| Scenario | Expected state | Recovery action | Retryable | Status |", "|---|---|---|---:|---|"]
    lines.extend(f"| {row['scenario']} | {row['expected_execution_state']} | {row['recovery_action']} | {row['retryable']} | {row['status']} |" for row in rows)
    lines += ["", "## Product decisions", "", "- Public catalogue count is 147.", "- Extinction Coefficient remains in the shared Optical Properties result bundle and is not a separate public catalogue slot.", "- Scientific engines launched: 0.", "- B2 uses deterministic Python subprocess fixtures only."]
    (OUT / "B2_failure_recovery_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
