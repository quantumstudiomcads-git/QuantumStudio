import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from runtime_agent.windows_job import (
    SuspendedProcess, WindowsJob, process_creation_time, process_exit_code, process_has_exited,
    windows_cancel_exit_codes, windows_creation_flags,
)


@unittest.skipUnless(os.name == "nt", "Windows Job Object APIs")
class WindowsJobOwnershipTests(unittest.TestCase):
    def test_all_job_termination_phases_are_classified_as_cancellation(self):
        self.assertTrue({0xD1F1, 0xD1F2, 0xD1F3}.issubset(windows_cancel_exit_codes()))

    def _launch_suspended(self, marker: Path):
        code = f"from pathlib import Path; import time; Path({str(marker)!r}).write_text('ready'); time.sleep(60)"
        return SuspendedProcess(sys.executable, ("-c", code), str(marker.parent),
                                {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
                                subprocess.DEVNULL, subprocess.DEVNULL, subprocess.DEVNULL,
                                windows_creation_flags())

    def test_documented_create_assign_verify_resume_and_cleanup_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); marker = root / "started.txt"
            process = self._launch_suspended(marker)
            job = WindowsJob()
            try:
                created = process_creation_time(process.pid)
                self.assertFalse(marker.exists())
                self.assertFalse(job.is_process_member(os.getpid(), process_creation_time(os.getpid())))
                self.assertEqual(job.assign_suspended_process(process), created)
                self.assertEqual(job.active_processes(), 1)
                self.assertFalse(marker.exists())
                job.resume_process(process, created)
                self.assertIsNone(process._thread_handle)
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(marker.exists())
                job.terminate()
                self.assertTrue(job.wait_empty(5))
                self.assertTrue(process_has_exited(process.pid, created),
                                f"pid={process.pid}; poll={process.poll()}; code={process_exit_code(process.pid, created)}; active={job.active_processes()}")
            finally:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=5)
                process.close()
                job_name = job.name
                job.close()
            self.assertIsNone(process._handle)
            self.assertIsNone(process._thread_handle)
            with self.assertRaises(OSError):
                WindowsJob(job_name, create=False)

    def test_create_process_failure_creates_no_owned_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); missing = root / "missing.exe"
            with self.assertRaises(OSError):
                SuspendedProcess(str(missing), (), str(root), {"PATH": ""}, subprocess.DEVNULL,
                                 subprocess.DEVNULL, subprocess.DEVNULL, windows_creation_flags())

    def test_assignment_failure_terminates_only_suspended_owned_handle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); marker = root / "must-not-start.txt"
            process = self._launch_suspended(marker); job = WindowsJob()
            creation = process_creation_time(process.pid)
            try:
                with patch.object(job._kernel, "AssignProcessToJobObject", return_value=0):
                    with self.assertRaises(OSError):
                        job.assign_suspended_process(process)
                self.assertFalse(marker.exists())
                process.kill(); process.wait(timeout=5)
                self.assertTrue(process_has_exited(process.pid, creation))
            finally:
                process.close(); job.close()

    def test_resume_failure_reaps_suspended_process_and_releases_handles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); marker = root / "must-not-start.txt"
            process = self._launch_suspended(marker); job = WindowsJob()
            creation = job.assign_suspended_process(process)
            try:
                with patch.object(job._kernel, "ResumeThread", return_value=0xFFFFFFFF):
                    with self.assertRaises(OSError):
                        job.resume_process(process, creation)
                self.assertFalse(marker.exists())
                process.kill(); process.wait(timeout=5)
                self.assertTrue(job.wait_empty(5))
            finally:
                process.close(); job.close()
            self.assertIsNone(process._handle)
            self.assertIsNone(process._thread_handle)

    def test_unrelated_sentinel_and_test_parent_are_outside_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "started.txt"
            process = self._launch_suspended(marker); job = WindowsJob()
            sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], shell=False)
            try:
                creation = job.assign_suspended_process(process)
                self.assertFalse(job.is_process_member(os.getpid(), process_creation_time(os.getpid())))
                self.assertFalse(job.is_process_member(sentinel.pid, process_creation_time(sentinel.pid)))
                job.resume_process(process, creation)
                job.terminate(); self.assertTrue(job.wait_empty(5))
                self.assertIsNone(sentinel.poll())
            finally:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=5)
                process.close(); job.close()
                if sentinel.poll() is None:
                    sentinel.terminate(); sentinel.wait(timeout=5)
