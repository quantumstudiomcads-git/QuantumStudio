import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backend.execution.models import TaskExecutionRecord, TaskState, WorkflowExecutionRecord
from backend.execution.recovery import (
    FailureClass, IllegalTaskTransition, classify_process_result, cleanup_disposable,
    disk_preflight, recover_stale_running, require_task_transition,
)


class B2RecoveryContractTests(unittest.TestCase):
    def test_legal_transitions_and_terminal_history(self):
        require_task_transition(TaskState.PENDING, TaskState.READY)
        require_task_transition(TaskState.READY, TaskState.RUNNING)
        require_task_transition(TaskState.RUNNING, TaskState.FAILED)
        require_task_transition(TaskState.FAILED, TaskState.READY, new_attempt=True)
        with self.assertRaises(IllegalTaskTransition):
            require_task_transition(TaskState.COMPLETED, TaskState.RUNNING)

    def test_stale_running_is_interrupted_without_pid_attachment(self):
        task = TaskExecutionRecord("t", state=TaskState.RUNNING, process_id=999999)
        record = WorkflowExecutionRecord("r", "/tmp/work", {"t": task})
        self.assertTrue(recover_stale_running(record))
        self.assertEqual(task.state, TaskState.INTERRUPTED)
        self.assertEqual(task.error_type, "INTERRUPTED")

    def test_failure_classification_is_conservative(self):
        self.assertIsNone(classify_process_result(0))
        self.assertEqual(classify_process_result(1), FailureClass.RETRYABLE_TRANSIENT)
        self.assertEqual(classify_process_result(-9), FailureClass.PROCESS_KILLED)
        self.assertEqual(classify_process_result(-9, oom_evidence=True), FailureClass.NONRETRYABLE_RESOURCE)
        self.assertEqual(classify_process_result(-15, cancelled=True), FailureClass.USER_CANCELLED)

    def test_disk_preflight_is_injectible(self):
        Usage = type("Usage", (), {"free": 99})
        result = disk_preflight(".", 100, usage=lambda _path: Usage())
        self.assertFalse(result.adequate)
        self.assertEqual(result.reason, "INSUFFICIENT_DISK_SPACE")

    def test_cleanup_is_contained_and_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root, external = Path(tmp), Path(outside)
            disposable = root / "staging"
            disposable.mkdir()
            (disposable / "partial").write_text("x")
            external_file = external / "keep.txt"
            external_file.write_text("keep")
            link = root / "link"
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)], check=True, capture_output=True)
            else:
                link.symlink_to(external, target_is_directory=True)
            cleanup_disposable(root, disposable)
            self.assertFalse(disposable.exists())
            cleanup_disposable(root, link)
            self.assertTrue(external_file.exists())
            with self.assertRaises(ValueError):
                cleanup_disposable(root, external)

    def test_fake_engine_behaviors_without_scientific_engines(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "fake.py"
            script.write_text("""import os, signal, sys\nmode=sys.argv[1]\nif mode=='success': open('artifact.dat','w').write('ok')\nelif mode=='missing': pass\nelif mode=='zero': open('artifact.dat','wb').close()\nelif mode=='malformed': open('artifact.dat','w').write('{bad')\nelif mode=='signal': os.kill(os.getpid(), signal.SIGTERM)\nelif mode=='exit': sys.exit(42)\n""")
            ok = subprocess.run([sys.executable, str(script), "success"], cwd=tmp, check=False)
            self.assertEqual(ok.returncode, 0)
            self.assertEqual((Path(tmp) / "artifact.dat").read_text(), "ok")
            exited = subprocess.run([sys.executable, str(script), "exit"], cwd=tmp, check=False)
            self.assertEqual(exited.returncode, 42)
            killed = subprocess.run([sys.executable, str(script), "signal"], cwd=tmp, check=False)
            self.assertEqual(killed.returncode, signal.SIGTERM if os.name == "nt" else -signal.SIGTERM)

    def test_failure_matrix_is_machine_readable(self):
        matrix = {
            "missing_executable": {"execution": "FAILED", "retryable": False},
            "nonzero_exit": {"execution": "FAILED", "retryable": True},
            "user_cancel": {"execution": "CANCELLED", "retryable": False},
            "stale_running": {"execution": "INTERRUPTED", "retryable": True},
            "missing_artifact": {"result": "PARSE_FAILED", "retryable": False},
            "disk_preflight": {"execution": "BLOCKED", "retryable": False},
        }
        self.assertEqual(json.loads(json.dumps(matrix))["stale_running"]["execution"], "INTERRUPTED")
