"""Fail-closed launch identity validation before native PID interpretation."""
import os
from contextlib import nullcontext
import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime_agent import agent
from runtime_agent.protocol import (
    AgentStatus,
    RuntimePath,
    RuntimeProcessRequest,
    WINDOWS_PROCESS_ID_MAX,
    is_valid_posix_process_identity,
    is_valid_windows_process_identity,
)


class _PosixOS:
    name = "posix"

    def __init__(self, *, pgid=None, pgid_error=None, current_group=99):
        self.pgid = pgid
        self.pgid_error = pgid_error
        self.current_group = current_group
        self.getpgid_calls = []
        self.getpgrp_calls = 0
        self.kill_calls = []
        self.killpg_calls = []

    def __getattr__(self, name):
        return getattr(os, name)

    def getpgid(self, pid):
        self.getpgid_calls.append(pid)
        if self.pgid_error is not None:
            raise self.pgid_error
        return self.pgid

    def getpgrp(self):
        self.getpgrp_calls += 1
        return self.current_group

    def kill(self, *args):
        self.kill_calls.append(args)

    def killpg(self, *args):
        self.killpg_calls.append(args)


class _Process:
    def __init__(self, pid, return_code=0):
        self.pid = pid
        self.return_code = return_code
        self.poll_calls = self.kill_calls = self.wait_calls = 0

    def poll(self):
        self.poll_calls += 1
        return None

    def kill(self):
        self.kill_calls += 1

    def wait(self, *args, **kwargs):
        self.wait_calls += 1
        return self.return_code


def _int_like():
    class IntLike:
        def __int__(self):
            return 1
    return IntLike()


def _int_subclass():
    class IntSubclass(int):
        pass
    return IntSubclass(1)


IDENTITIES = (
    None, False, True, -2_147_483_649, -2_147_483_648, -1, 0, 1, 2,
    32_768, 4_194_304, 2_147_483_646, 2_147_483_647, 2_147_483_648,
    4_294_967_295, 10**60, 1.0, 1.5, "1", "2147483647", "", " ",
    [], (), {}, _int_like(), _int_subclass(),
)


class LaunchIdentityOrderingTests(unittest.TestCase):
    def _request(self, task_id):
        return RuntimeProcessRequest(task_id, RuntimePath("/safe/app"), (),
                                     RuntimePath("/safe/work"), {})

    def _run(self, root, task_id, pid, *, pgid=None, pgid_error=None,
             process_start="123456", persist=True):
        process = _Process(pid)
        native = _PosixOS(pgid=pgid, pgid_error=pgid_error)
        start_calls = []
        executable = Path(sys.executable)
        cwd = Path(root)
        atomic = inspect.getclosurevars(agent._atomic_json).nonlocals.get(
            "original_atomic", agent._atomic_json)
        process_type = agent.subprocess.Popen
        launched = []

        class FakePopen(process_type):
            def __init__(self, *_args, **_kwargs):
                self.pid = pid
                self._child_created = True
                self.returncode = None
                self.return_code = 0
                self.poll_calls = self.kill_calls = self.wait_calls = 0
                launched.append(self)

            def _internal_poll(self, **kwargs):
                # Exercise the real inherited Popen destructor without an OS call.
                native.destructor_polls += 1
                self.returncode = 0

            def poll(self):
                self.poll_calls += 1
                return None

            def kill(self):
                self.kill_calls += 1

            def wait(self, *args, **kwargs):
                self.wait_calls += 1
                return self.return_code

        native.destructor_polls = 0
        patches = [
            patch.object(agent, "os", native),
            patch.object(agent, "_under", return_value=True),
            patch.object(agent, "_real_under", return_value=True),
            patch.object(agent, "_host_path", side_effect=[executable, cwd]),
            patch.object(agent, "_proc_start_ticks",
                         side_effect=lambda value: (start_calls.append(value) or process_start)),
            patch.object(agent, "_task_record_lock", side_effect=lambda *_a, **_k: nullcontext()),
            patch.object(agent.subprocess, "Popen", FakePopen),
            patch.object(agent, "_atomic_json",
                         side_effect=atomic if persist else OSError("injected persistence failure")),
        ]
        with (patches[0], patches[1], patches[2], patches[3],
              patches[4], patches[5], patches[6], patches[7]):
            result = agent.execute_request(
                self._request(task_id), trusted_executable_roots=("/safe",),
                trusted_working_roots=("/safe",), task_control_root=str(root),
                enable_task_control=True)
        process = launched.pop()
        if not is_valid_posix_process_identity(pid):
            process.__del__()
        return result, process, native, start_calls

    def test_launch_pid_matrix_is_validated_before_any_pid_native_or_cleanup_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index, pid in enumerate(IDENTITIES):
                with self.subTest(pid=repr(pid)):
                    valid = is_valid_posix_process_identity(pid)
                    pgid = pid if valid else 7
                    result, process, native, start_calls = self._run(
                        tmp, f"pid-matrix-{index}", pid, pgid=pgid)
                    if not valid:
                        self.assertEqual(native.destructor_polls, 0)
                        self.assertEqual(result.status, AgentStatus.TASK_OUTCOME_INDETERMINATE)
                        self.assertEqual(native.getpgid_calls, [])
                        self.assertEqual(native.getpgrp_calls, 0)
                        self.assertEqual(start_calls, [])
                        self.assertEqual(native.kill_calls, [])
                        self.assertEqual(native.killpg_calls, [])
                        self.assertEqual((process.poll_calls, process.kill_calls, process.wait_calls), (0, 0, 0))
                        self.assertIsNone(result.return_code)
                        self.assertIsNone(result.runtime_pid)
                        status = agent.task_status(f"pid-matrix-{index}", task_control_root=tmp)
                        saved = agent._read_control(f"pid-matrix-{index}", tmp)
                        self.assertEqual(status["status"], "TASK_OUTCOME_INDETERMINATE")
                        self.assertEqual(saved["state"], "OUTCOME_INDETERMINATE")
                        self.assertEqual(saved["failure_code"], "invalid_launch_process_identity")
                        self.assertNotIn("pid", saved)
                        self.assertNotIn("pgid", saved)
                        cancelled = agent.cancel_task(f"pid-matrix-{index}", task_control_root=tmp)
                        self.assertEqual(cancelled["status"], "TASK_OUTCOME_INDETERMINATE")
                        self.assertEqual(native.killpg_calls, [])
                    elif pid == 1:
                        self.assertEqual(result.status, AgentStatus.TASK_OUTCOME_INDETERMINATE)
                        self.assertEqual(native.getpgid_calls, [1])
                        self.assertEqual(start_calls, [])
                    else:
                        self.assertEqual(result.status, AgentStatus.PROCESS_EXITED)
                        self.assertEqual(native.getpgid_calls, [pid])
                        self.assertEqual(start_calls, [pid])

    def test_invalid_process_group_results_fail_before_creation_lookup(self):
        invalid_groups = (None, False, True, -1, 0, 2_147_483_648,
                          10**60, 1.0, "345", [])
        with tempfile.TemporaryDirectory() as tmp:
            for index, pgid in enumerate(invalid_groups):
                with self.subTest(pgid=repr(pgid)):
                    result, process, native, start_calls = self._run(
                        tmp, f"pgid-matrix-{index}", 345, pgid=pgid)
                    self.assertEqual(result.status, AgentStatus.TASK_OUTCOME_INDETERMINATE)
                    self.assertEqual(native.getpgid_calls, [345])
                    self.assertEqual(native.getpgrp_calls, 0)
                    self.assertEqual(start_calls, [])
                    self.assertEqual(native.kill_calls, [])
                    self.assertEqual(native.killpg_calls, [])
                    self.assertEqual((process.poll_calls, process.kill_calls, process.wait_calls), (0, 0, 0))

    def test_group_lookup_os_errors_and_mismatched_group_are_indeterminate(self):
        errors = (ProcessLookupError("gone"), PermissionError("denied"), OSError("failure"),
                  TypeError("malformed"), OverflowError("too large"))
        with tempfile.TemporaryDirectory() as tmp:
            for index, error in enumerate(errors):
                with self.subTest(error=type(error).__name__):
                    result, _, native, start_calls = self._run(
                        tmp, f"pgid-error-{index}", 345, pgid_error=error)
                    self.assertEqual(result.status, AgentStatus.TASK_OUTCOME_INDETERMINATE)
                    self.assertEqual(native.getpgid_calls, [345])
                    self.assertEqual(start_calls, [])
            result, _, native, start_calls = self._run(tmp, "pgid-mismatch", 345, pgid=346)
            self.assertEqual(result.status, AgentStatus.TASK_OUTCOME_INDETERMINATE)
            self.assertEqual(native.getpgrp_calls, 0)
            self.assertEqual(start_calls, [])

    def test_identity_terminal_write_failure_is_typed_and_never_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, process, native, start_calls = self._run(
                tmp, "identity-write-failure", 10**60, persist=False)
            self.assertEqual(result.status, AgentStatus.TASK_CONTROL_PERSISTENCE_FAILED)
            self.assertTrue(result.started)
            self.assertFalse(result.finished)
            self.assertEqual(result.diagnostic, "task_control_persistence_failed")
            self.assertEqual(native.getpgid_calls, [])
            self.assertEqual(start_calls, [])
            self.assertEqual(native.kill_calls, [])
            self.assertEqual(native.killpg_calls, [])
            self.assertEqual((process.poll_calls, process.kill_calls, process.wait_calls), (0, 0, 0))
            self.assertIsNone(agent._read_control("identity-write-failure", tmp))

    def test_windows_pid_range_is_distinct_and_native_lookup_rejects_invalid_values_first(self):
        self.assertTrue(is_valid_windows_process_identity(1))
        self.assertTrue(is_valid_windows_process_identity(WINDOWS_PROCESS_ID_MAX))
        for value in (None, False, True, 0, -1, WINDOWS_PROCESS_ID_MAX + 1, 10**60, "123"):
            with self.subTest(value=repr(value)):
                self.assertFalse(is_valid_windows_process_identity(value))
        import runtime_agent.windows_job as windows_job
        with patch.object(windows_job, "_kernel32") as kernel:
            for value in (0, False, True, WINDOWS_PROCESS_ID_MAX + 1, 10**60):
                with self.subTest(native_pid=repr(value)):
                    with self.assertRaises(ValueError):
                        windows_job.process_creation_time(value)
            kernel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
