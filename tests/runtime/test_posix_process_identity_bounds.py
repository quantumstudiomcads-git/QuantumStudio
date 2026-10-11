"""Finite POSIX process identities for persisted runtime cancellation evidence."""
import json
import inspect
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

from runtime_agent import agent
from runtime_agent.protocol import (
    POSIX_PROCESS_ID_MAX,
    POSIX_PROCESS_ID_MIN,
    is_valid_posix_process_identity,
)


IDENTITIES = (
    None, False, True, -2_147_483_649, -2_147_483_648, -1, 0, 1, 2,
    32_768, 4_194_304, 2_147_483_646, 2_147_483_647, 2_147_483_648,
    4_294_967_295, 10**60, 1.0, 1.5, "1", "2147483647", "1e6", "",
    " ", [], {}, (),
)


def expected_valid(value):
    return type(value) is int and POSIX_PROCESS_ID_MIN <= value <= POSIX_PROCESS_ID_MAX


class PosixProcessIdentityBoundsTests(unittest.TestCase):
    def test_protocol_validator_and_record_boundary_cover_the_full_value_matrix(self):
        for value in IDENTITIES:
            with self.subTest(value=repr(value)):
                expected = expected_valid(value)
                self.assertEqual(is_valid_posix_process_identity(value), expected)
                record = {"boundary_type": "posix_session", "pid": 345, "pgid": value}
                self.assertEqual(agent._process_boundary_identity(record) is not None, expected)

                record["pid"] = value
                record["pgid"] = 345
                self.assertEqual(agent._process_boundary_identity(record) is not None, expected)

    def test_prepare_receipt_and_evidence_validation_use_the_same_range(self):
        token, request = "a" * 32, "b" * 32
        for index, value in enumerate(IDENTITIES):
            with self.subTest(value=repr(value)):
                expected = expected_valid(value)
                record = {
                    "task_id": f"range-{index}", "state": "CANCELLING",
                    "cancel_requested": True, "cancel_token": request,
                    "ownership_token": token, "pid": 345,
                    "process_creation_time": "678", "boundary_type": "posix_session",
                    "pgid": value,
                }
                if not expected:
                    with self.assertRaises(ValueError):
                        agent._prepare_cancellation_action(
                            record, action="graceful", ownership=token,
                            request_id=request, pid=345, creation_time=678)
                    continue
                prepared = agent._prepare_cancellation_action(
                    record, action="graceful", ownership=token,
                    request_id=request, pid=345, creation_time=678)
                confirmed = agent._with_cancellation_action(
                    prepared, action="graceful", ownership=token,
                    request_id=request, pid=345, creation_time=678)
                self.assertEqual(agent._cancellation_action_evidence(
                    confirmed, ownership=token, request_id=request,
                    pid=345, creation_time=678), "graceful")

    def test_matching_but_invalid_record_intent_and_receipt_reconcile_indeterminate(self):
        token, request = "a" * 32, "b" * 32
        invalid_values = tuple(value for value in IDENTITIES if not expected_valid(value))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, value in enumerate(invalid_values):
                task_id = f"invalid-range-{index}"
                invalid_id = str(value)
                intent = {
                    "version": 2, "state": "confirmed", "task_id": task_id,
                    "request_id": request, "attempt_id": "c" * 32,
                    "ownership_token": token, "pid": 345,
                    "process_creation_time": "678", "boundary_type": "posix_session",
                    "boundary_id": invalid_id, "action": "graceful",
                    "prepared_at": "2026-10-10T12:00:00Z",
                }
                receipt = {
                    "version": 2, "task_id": task_id, "request_id": request,
                    "attempt_id": intent["attempt_id"], "ownership_token": token,
                    "pid": 345, "process_creation_time": "678",
                    "boundary_type": "posix_session", "boundary_id": invalid_id,
                    "action": "graceful", "action_at": "2026-10-10T12:00:01Z",
                }
                record = {
                    "task_id": task_id, "state": "CANCELLING", "cancel_requested": True,
                    "cancel_token": request, "ownership_token": token, "pid": 345,
                    "process_creation_time": "678", "boundary_type": "posix_session",
                    "pgid": value, "return_code": 0,
                    "cancellation_action_intent": intent,
                    "cancellation_action_attempts": [intent],
                    "cancellation_action_evidence": receipt,
                    "cancellation_action_receipts": [receipt],
                }
                path = root / f"{task_id}.json"
                path.write_text(json.dumps(record), encoding="utf-8")
                with patch.object(agent, "_record_alive", return_value=False):
                    status = agent.task_status(task_id, task_control_root=tmp)
                stored = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(status["status"], "TASK_CANCELLATION_INDETERMINATE")
                self.assertEqual(stored["state"], "CANCELLATION_INDETERMINATE")

    def test_native_posix_signal_guard_rejects_invalid_values_without_calling_os(self):
        invalid_values = tuple(value for value in IDENTITIES if not expected_valid(value))
        signal_guard = agent._signal_group
        signal_guard = inspect.getclosurevars(signal_guard).nonlocals.get("original_group", signal_guard)
        with patch.object(agent.os, "name", "posix"), \
             patch.object(agent.os, "killpg", create=True) as killpg:
            for value in invalid_values:
                with self.subTest(value=repr(value)):
                    with self.assertRaises(ValueError):
                        signal_guard(value, signal.SIGTERM)
            killpg.assert_not_called()

    def test_cancel_and_reconciliation_never_turn_invalid_identity_into_success(self):
        invalid_values = tuple(value for value in IDENTITIES if not expected_valid(value))
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, value in enumerate(invalid_values):
                for field in ("pid", "pgid"):
                    with self.subTest(value=repr(value), field=field):
                        task_id = f"bad-native-id-{index}-{field}"
                        record = {
                            "task_id": task_id, "state": "RUNNING",
                            "boundary_type": "posix_session", "pid": 345,
                            "pgid": 345, "process_start_ticks": "untrusted",
                            "process_creation_time": "untrusted", "return_code": 0,
                            "ownership_token": "a" * 32,
                        }
                        record[field] = value
                        path = root / f"{task_id}.json"
                        path.write_text(json.dumps(record), encoding="utf-8")
                        atomic_writer = inspect.getclosurevars(agent._atomic_json).nonlocals.get(
                            "original_atomic", agent._atomic_json)
                        with patch.object(agent.os, "name", "posix"), \
                             patch.object(agent, "_signal_group") as signal_group, \
                             patch.object(agent, "_task_record_lock", side_effect=lambda *_a, **_k: nullcontext()), \
                             patch.object(agent, "_control_path", return_value=path), \
                             patch.object(agent, "_atomic_json", side_effect=atomic_writer):
                            cancelled = agent.cancel_task(task_id, task_control_root=tmp)
                            status = agent.task_status(task_id, task_control_root=tmp)
                        stored = json.loads(path.read_text(encoding="utf-8"))
                        self.assertEqual(cancelled["status"], "TASK_OUTCOME_INDETERMINATE")
                        self.assertEqual(status["status"], "TASK_OUTCOME_INDETERMINATE")
                        self.assertEqual(stored["failure_code"], "task_process_identity_unproven")
                        self.assertNotEqual(stored["state"], "FINISHED")
                        signal_group.assert_not_called()

    def test_json_round_trip_keeps_finite_integer_semantics(self):
        maximum = json.loads(json.dumps(POSIX_PROCESS_ID_MAX))
        too_large = json.loads(json.dumps(POSIX_PROCESS_ID_MAX + 1))
        huge = json.loads(json.dumps(10**60))
        self.assertEqual(maximum, POSIX_PROCESS_ID_MAX)
        self.assertTrue(is_valid_posix_process_identity(maximum))
        self.assertFalse(is_valid_posix_process_identity(too_large))
        self.assertFalse(is_valid_posix_process_identity(huge))
        for value in ("1e6", "2147483647", 1.0, True):
            decoded = json.loads(json.dumps(value))
            self.assertFalse(is_valid_posix_process_identity(decoded))


if __name__ == "__main__":
    unittest.main()
