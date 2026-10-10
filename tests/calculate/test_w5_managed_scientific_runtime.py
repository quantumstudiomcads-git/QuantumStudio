import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.runtime.engine_pack import sha256_file
from backend.runtime.managed_science import (
    ArtifactRole, ArtifactTransferError, EnginePackConflictError, EnginePackDescriptor,
    EnginePackIntegrityError, ManagedEnginePackInstaller, StageInArtifact, StageOutArtifact,
    discover_managed_engine_family, managed_execution_directory, ManagedRuntimeArtifactTransport, ManagedEnginePackDeployment,
)
from runtime_agent.agent import cancel_task, execute_request, stage_in, stage_out, task_status
from runtime_agent.protocol import AgentStatus, RuntimePath, RuntimeProcessRequest
from backend.runtime.wsl import WSLCommandResult
from backend.execution.persistence import ExecutionStore
from backend.execution.models import TaskExecutionRecord, TaskState, WorkflowExecutionRecord
from frontend.services.result_service import ResultService
from tests.helpers.fake_executable import runtime_path, write_python_fixture


def make_pack(root: Path, *, version="1.0", platform="linux", architecture="x86_64", body=b"fake engine"):
    (root / "bin").mkdir(parents=True, exist_ok=True)
    tool = root / "bin" / "fake-tool"; tool.write_bytes(body); tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    manifest = {"schema_version": "1", "engine_pack_version": version, "platform": platform, "architecture": architecture,
                "family": "QE_EP6", "qe_version": "7.6", "epw_version": "6.1", "wannier_version": "3.1.0",
                "engines": [{"tool_id": "pw.x", "executable": "pw.x", "relative_path": "bin/fake-tool", "sha256": sha256_file(tool)}]}
    (root / "engine-pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


class ManagedEnginePackTests(unittest.TestCase):
    def test_verified_local_pack_install_is_atomic_idempotent_and_discovers_runtime_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source Ω"; make_pack(source)
            descriptor = EnginePackDescriptor("beta", source, sha256_file(source / "engine-pack.json"))
            installer = ManagedEnginePackInstaller(root / "runtime-engines")
            first = installer.install(descriptor); second = installer.install(descriptor)
            self.assertTrue(first.changed); self.assertFalse(second.changed)
            family = discover_managed_engine_family(first.installed_root, pack_id="beta")
            self.assertEqual(str(family.resolve("pw.x")), "/opt/quantumstudio/engines/packs/beta-1.0/bin/fake-tool")
            self.assertEqual(family.family.qe_version, "7.6")
            self.assertNotIn("PATH", str(family.tools))

    def test_integrity_platform_unknown_content_and_same_version_conflict_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"; make_pack(source)
            descriptor = EnginePackDescriptor("beta", source, sha256_file(source / "engine-pack.json"))
            unknown = root / "unknown"; unknown.mkdir(); (unknown / "unrelated").write_text("x")
            with self.assertRaises(EnginePackConflictError): ManagedEnginePackInstaller(unknown).install(descriptor)
            tool = source / "bin" / "fake-tool"; tool.write_bytes(b"tampered")
            with self.assertRaises(EnginePackIntegrityError): ManagedEnginePackInstaller(root / "engines").install(descriptor)
            make_pack(source, platform="windows")
            bad = EnginePackDescriptor("beta", source, sha256_file(source / "engine-pack.json"))
            with self.assertRaises(EnginePackIntegrityError): ManagedEnginePackInstaller(root / "engines").install(bad)

    def test_managed_execution_identity_rejects_traversal(self):
        self.assertEqual(str(managed_execution_directory("request", "execution", "task")), "/var/lib/quantumstudio/workflows/request/executions/execution/task")
        with self.assertRaises(Exception): managed_execution_directory("../request", "execution", "task")


class AgentTransferAndControlTests(unittest.TestCase):
    def test_binary_stage_in_out_is_atomic_sha_checked_and_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); workflows = root / "workflows"; pseudo = root / "pseudos"; destination = workflows / "w" / "input.bin"; source = root / "source.bin"
            payload = b"\x00input " + "Ω".encode("utf-8") + b"\xff"; source.write_bytes(payload)
            header = {"schema_version": 1, "operation": "stage_in", "destination": runtime_path(destination), "sha256": hashlib.sha256(payload).hexdigest()}
            with source.open("rb") as stream: result = stage_in(header, stream, trusted_roots=(runtime_path(workflows), runtime_path(pseudo)))
            self.assertEqual(result["sha256"], hashlib.sha256(payload).hexdigest()); self.assertEqual(destination.read_bytes(), payload)
            collected = root / "collected.bin"
            with collected.open("wb") as output: stage_out({"schema_version": 1, "operation": "stage_out", "source": runtime_path(destination)}, output, trusted_roots=(runtime_path(workflows), runtime_path(pseudo)))
            self.assertEqual(collected.read_bytes(), payload)
            bad = {"schema_version": 1, "operation": "stage_in", "destination": "/etc/not-allowed", "sha256": ""}
            with source.open("rb") as stream:
                with self.assertRaises(Exception): stage_in(bad, stream, trusted_roots=(runtime_path(workflows), runtime_path(pseudo)))
            self.assertFalse((destination.parent / "input.bin.qs-stage.tmp").exists())

    def test_task_control_uses_owned_task_record_and_process_group_cancellation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); engines, work, records = root / "engines", root / "workflows", root / "tasks"; engines.mkdir(); cwd = work / "task"; cwd.mkdir(parents=True)
            ready = cwd / "ready.txt"
            fake = write_python_fixture(engines / "long_running.py", f"import os,signal,time\nfrom pathlib import Path\nif os.name != 'nt':\n signal.signal(signal.SIGTERM, signal.SIG_IGN)\nelse:\n signal.signal(signal.SIGBREAK, signal.SIG_IGN)\nPath({str(ready)!r}).write_text('ready')\nwhile True:\n time.sleep(.05)\n")
            request = RuntimeProcessRequest("owned-task", RuntimePath(runtime_path(sys.executable)), (runtime_path(fake),), RuntimePath(runtime_path(cwd)), {})
            result = []
            thread = threading.Thread(target=lambda: result.append(execute_request(request, trusted_executable_roots=(runtime_path(Path(sys.executable).parent),), trusted_working_roots=(runtime_path(work),), task_control_root=str(records), enable_task_control=True)), daemon=True)
            thread.start()
            for _ in range(100):
                if task_status("owned-task", task_control_root=str(records))["status"] == AgentStatus.TASK_RUNNING.value: break
                time.sleep(.02)
            for _ in range(250):
                if ready.exists(): break
                time.sleep(.02)
            self.assertTrue(ready.exists(), "synthetic child did not install its graceful handler")
            self.assertEqual(task_status("owned-task", task_control_root=str(records))["status"], AgentStatus.TASK_RUNNING.value)
            cancelled = cancel_task("owned-task", grace_seconds=.05, task_control_root=str(records))
            self.assertEqual(cancelled["status"], AgentStatus.TASK_CANCELLED.value)
            thread.join(3); self.assertFalse(thread.is_alive())
            self.assertEqual(cancelled["outcome"], "terminated" if os.name == "nt" else "KILLED_AFTER_GRACE")
            allowed_codes = (-9, None, 15, 0xC000013A, 0xD1F1) if os.name == "nt" else (-9, None)
            self.assertIn(result[0].return_code, allowed_codes); self.assertIn(result[0].status, {AgentStatus.PROCESS_EXITED, AgentStatus.INTERNAL_AGENT_ERROR}, result[0].diagnostic)
            self.assertEqual(task_status("owned-task", task_control_root=str(records))["status"], AgentStatus.TASK_CANCELLED.value)
            repeated = cancel_task("owned-task", grace_seconds=.05, task_control_root=str(records))
            self.assertEqual(repeated["status"], AgentStatus.TASK_CANCELLED.value)
            self.assertEqual(repeated["outcome"], cancelled["outcome"])
            with self.assertRaises(Exception): cancel_task("../not-a-task", task_control_root=str(records))

    @unittest.skipUnless(os.name == "nt", "Windows graceful cancellation outcome test")
    def test_handled_ctrl_break_code_zero_is_recorded_as_cancelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); engines, work, records = root / "engines", root / "workflows", root / "tasks"
            engines.mkdir(); cwd = work / "task"; cwd.mkdir(parents=True)
            grandchild_ready, grandchild_event = cwd / "grandchild-ready", cwd / "grandchild-break"
            child_ready, child_event = cwd / "child-ready", cwd / "child-break"
            grandchild = write_python_fixture(engines / "graceful_grandchild.py", f"""import signal, time
from pathlib import Path
ready = Path({str(grandchild_ready)!r})
event = Path({str(grandchild_event)!r})
def stop(sig, frame):
    event.write_text('handled')
    raise SystemExit(0)
signal.signal(signal.SIGBREAK, stop)
ready.write_text('ready')
while True: time.sleep(.02)
""")
            child = write_python_fixture(engines / "graceful_child.py", f"""import signal, subprocess, sys, time
from pathlib import Path
ready = Path({str(child_ready)!r})
event = Path({str(child_event)!r})
def stop(sig, frame):
    event.write_text('handled')
    raise SystemExit(0)
signal.signal(signal.SIGBREAK, stop)
subprocess.Popen([sys.executable, {str(grandchild)!r}], shell=False)
deadline = time.monotonic() + 5
while not Path({str(grandchild_ready)!r}).exists() and time.monotonic() < deadline:
    time.sleep(.01)
ready.write_text('ready')
while True: time.sleep(.02)
""")
            request = RuntimeProcessRequest("graceful-zero", RuntimePath(runtime_path(sys.executable)),
                (runtime_path(child),),
                RuntimePath(runtime_path(cwd)), {})
            results = []
            worker = threading.Thread(target=lambda: results.append(execute_request(
                request, trusted_executable_roots=(runtime_path(Path(sys.executable).parent),),
                trusted_working_roots=(runtime_path(work),), task_control_root=str(records),
                enable_task_control=True)), daemon=True)
            worker.start()
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if child_ready.exists(): break
                    time.sleep(.02)
                self.assertTrue(child_ready.exists(),
                    f"synthetic process tree did not become ready; results={results!r}; records={list(records.glob('*'))!r}")
                result = cancel_task("graceful-zero", grace_seconds=3, task_control_root=str(records))
                worker.join(8)
                self.assertFalse(worker.is_alive())
                self.assertEqual(result["status"], AgentStatus.TASK_CANCELLED.value)
                self.assertEqual(result["outcome"], "graceful")
                self.assertTrue(child_event.exists())
                self.assertTrue(grandchild_event.exists())
                record = json.loads((records / "graceful-zero.json").read_text(encoding="utf-8"))
                self.assertEqual(record["state"], "CANCELLED")
                self.assertEqual(record["return_code"], 0)
                self.assertEqual(record["cancellation_outcome"], "graceful")
                evidence = record["cancellation_action_evidence"]
                self.assertEqual(evidence["action"], "graceful")
                self.assertEqual(evidence["pid"], record["pid"])
                self.assertEqual(evidence["process_creation_time"], record["process_creation_time"])
            finally:
                if worker.is_alive():
                    cancel_task("graceful-zero", grace_seconds=.1, task_control_root=str(records))
                    worker.join(5)

    def test_cancellation_action_evidence_requires_matching_request_and_process(self):
        from runtime_agent.agent import _cancellation_action_evidence
        record = {"task_id": "evidence-task", "cancel_requested": True, "cancel_token": "a" * 32}
        record["cancellation_action_evidence"] = {
            "version": 1, "task_id": "evidence-task", "request_id": "a" * 32, "ownership_token": "b" * 32,
            "pid": 123, "process_creation_time": "456", "action": "graceful", "action_at": "now"}
        kwargs = {"ownership": "b" * 32, "request_id": "a" * 32, "pid": 123, "creation_time": 456}
        self.assertEqual(_cancellation_action_evidence(record, **kwargs), "graceful")
        self.assertIsNone(_cancellation_action_evidence(record, **{**kwargs, "pid": 124}))
        self.assertIsNone(_cancellation_action_evidence(record, **{**kwargs, "creation_time": 457}))
        self.assertIsNone(_cancellation_action_evidence(record, **{**kwargs, "request_id": "c" * 32}))
        copied = dict(record); copied["task_id"] = "another-task"
        self.assertIsNone(_cancellation_action_evidence(copied, **kwargs))
        malformed = dict(record); malformed["cancellation_action_evidence"] = {"version": 1, "action": "graceful"}
        self.assertIsNone(_cancellation_action_evidence(malformed, **kwargs))

    @unittest.skipUnless(os.name == "nt", "Windows natural-exit cancellation race test")
    def test_failed_graceful_delivery_and_natural_exit_are_not_classified_cancelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); task_id = "delivery-lost-race"; token = "d" * 32
            record = {"schema_version": 1, "task_id": task_id, "state": "RUNNING",
                      "pid": os.getpid(), "ownership_token": token,
                      "boundary_type": "windows_job_object+process_group",
                      "job_name": "Local\\QSRuntime-" + token, "process_creation_time": "1236"}
            (root / f"{task_id}.json").write_text(json.dumps(record), encoding="utf-8")
            class ExitingJob:
                def __init__(self, *_args, **_kwargs): pass
                def active_processes(self): return 1
                def is_process_member(self, *_args): return True
                def send_ctrl_break(self, *_args, **_kwargs): raise AssertionError("exited process must not be signalled")
                def terminate(self, *_args): raise AssertionError("natural exit must not be terminated")
                def close(self): pass
                def __enter__(self): return self
                def __exit__(self, *_args): self.close()
            with patch("runtime_agent.windows_job.WindowsJob", ExitingJob), \
                    patch("runtime_agent.windows_job.process_exit_state", side_effect=[False, True]):
                result = cancel_task(task_id, grace_seconds=0, task_control_root=str(root))
            final = json.loads((root / f"{task_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], AgentStatus.TASK_FINISHED.value)
            self.assertEqual(final["state"], "FINISHED")
            self.assertNotIn("cancellation_action_evidence", final)
            self.assertEqual(final["cancellation_outcome"], "lost_natural_completion_race")

    @unittest.skipUnless(os.name == "nt", "Windows cancellation escalation race test")
    def test_empty_job_during_terminate_does_not_create_cancellation_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_id = "empty-job-race"; token = "e" * 32; root = Path(tmp)
            record = {"schema_version": 1, "task_id": task_id, "state": "RUNNING",
                      "pid": os.getpid(), "ownership_token": token,
                      "boundary_type": "windows_job_object+process_group",
                      "job_name": "Local\\QSRuntime-" + token, "process_creation_time": "1237"}
            (root / f"{task_id}.json").write_text(json.dumps(record), encoding="utf-8")
            class EmptyingJob:
                active_checks = iter((1, 1, 0, 0, 0, 0))
                def __init__(self, *_args, **_kwargs): pass
                def active_processes(self): return next(type(self).active_checks)
                def is_process_member(self, *_args): return True
                def send_ctrl_break(self, *_args, **_kwargs): return False
                def terminate(self, *_args): return self.active_processes() > 0
                def close(self): pass
                def __enter__(self): return self
                def __exit__(self, *_args): self.close()
            with patch("runtime_agent.windows_job.WindowsJob", EmptyingJob), \
                    patch("runtime_agent.windows_job.process_exit_state", return_value=False):
                result = cancel_task(task_id, grace_seconds=0, task_control_root=str(root))
            final = json.loads((root / f"{task_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], AgentStatus.TASK_FINISHED.value)
            self.assertEqual(final["state"], "FINISHED")
            self.assertNotIn("cancellation_action_evidence", final)
            self.assertEqual(final["cancellation_outcome"], "lost_natural_completion_race")

    def test_terminal_task_records_are_never_signalled_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for state in ("FINISHED", "FAILED", "CANCELLED"):
                task_id = "terminal-" + state.lower()
                record = {"schema_version": 1, "task_id": task_id, "state": state,
                          "pid": os.getpid() + 10_000_000, "ownership_token": "0" * 32}
                (root / f"{task_id}.json").write_text(json.dumps(record), encoding="utf-8")
                result = cancel_task(task_id, task_control_root=str(root))
                expected = AgentStatus.TASK_CANCELLED.value if state == "CANCELLED" else AgentStatus.TASK_FINISHED.value
                self.assertEqual(result["status"], expected)
                self.assertEqual(json.loads((root / f"{task_id}.json").read_text()) , record)

    def test_windows_creation_flags_include_an_independent_process_group(self):
        from runtime_agent.windows_job import windows_creation_flags
        flags = windows_creation_flags()
        self.assertTrue(flags & 0x00000200)  # CREATE_NEW_PROCESS_GROUP
        self.assertTrue(flags & 0x00000004)  # CREATE_SUSPENDED until Job assignment

    def test_missing_ownership_token_fails_without_opening_or_signalling_a_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); task_id = "missing-token"
            record = {"schema_version": 1, "task_id": task_id, "state": "RUNNING", "pid": os.getpid() + 10_000_000,
                      "ownership_token": "", "boundary_type": "windows_job_object+process_group",
                      "job_name": "Local\\QSRuntime-" + "0" * 32, "process_creation_time": "1"}
            (root / f"{task_id}.json").write_text(json.dumps(record), encoding="utf-8")
            result = cancel_task(task_id, task_control_root=str(root))
            self.assertEqual(result["status"], "FAILED")
            self.assertIn("ownership", result["diagnostic"].lower())
            self.assertEqual(json.loads((root / f"{task_id}.json").read_text(encoding="utf-8")), record)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object membership test")
    def test_mismatched_process_identity_fails_without_signalling(self):
        from runtime_agent.windows_job import WindowsJob
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); task_id = "stale-identity"; token = "a" * 32
            record = {"schema_version": 1, "task_id": task_id, "state": "RUNNING", "pid": os.getpid() + 10_000_000,
                      "ownership_token": token, "boundary_type": "windows_job_object+process_group",
                      "job_name": "Local\\QSRuntime-" + token, "process_creation_time": "123"}
            (root / f"{task_id}.json").write_text(json.dumps(record), encoding="utf-8")
            class NonMemberJob:
                def __init__(self, *_args, **_kwargs): pass
                def active_processes(self): return 1
                def is_process_member(self, *_args): return False
                def send_ctrl_break(self, *_args, **_kwargs): raise AssertionError("signal must not be sent")
                def close(self): pass
            with patch("runtime_agent.windows_job.WindowsJob", NonMemberJob), \
                    patch("runtime_agent.windows_job.process_exit_state", return_value=False):
                result = cancel_task(task_id, task_control_root=str(root))
            self.assertEqual(result["status"], "FAILED")
            self.assertIn("identity", result["diagnostic"].lower())
            self.assertEqual(json.loads((root / f"{task_id}.json").read_text(encoding="utf-8")), record)

    @unittest.skipUnless(os.name == "nt", "Windows cancellation terminal-race test")
    def test_graceful_action_preceding_clean_exit_finalization_classifies_cancelled(self):
        import runtime_agent.agent as agent
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); task_id = "natural-finish-race"; token = "b" * 32
            record = {"schema_version": 1, "task_id": task_id, "state": "RUNNING", "pid": os.getpid() + 10_000_000,
                      "ownership_token": token, "boundary_type": "windows_job_object+process_group",
                      "job_name": "Local\\QSRuntime-" + token, "process_creation_time": "1234"}
            (root / f"{task_id}.json").write_text(json.dumps(record), encoding="utf-8")
            event = threading.Event(); calls = {"graceful": 0, "terminate": 0}
            class RacingJob:
                def __init__(self, *_args, **_kwargs): pass
                def active_processes(self): return 1
                def is_process_member(self, *_args): return True
                def send_ctrl_break(self, *_args, **_kwargs):
                    calls["graceful"] += 1; event.set(); return True
                def terminate(self, *_args): calls["terminate"] += 1
                def close(self): pass
                def __enter__(self): return self
                def __exit__(self, *_args): self.close()
            def publish_finished():
                event.wait(2)
                with agent._task_record_lock(task_id, str(root)):
                    latest = agent._read_control(task_id, str(root))
                    action = agent._cancellation_action_evidence(
                        latest, ownership=token, request_id=str(latest.get("cancel_token", "")),
                        pid=int(latest["pid"]), creation_time=1234)
                    latest.update({"state": "CANCELLED" if action else "FINISHED", "return_code": 0})
                    agent._atomic_json(agent._control_path(task_id, str(root)), latest)
            publisher = threading.Thread(target=publish_finished, daemon=True)
            with patch("runtime_agent.windows_job.WindowsJob", RacingJob), \
                    patch("runtime_agent.windows_job.process_exit_state", return_value=False):
                publisher.start()
                result = cancel_task(task_id, grace_seconds=.3, task_control_root=str(root))
                publisher.join(2)
                self.assertFalse(publisher.is_alive())
            self.assertEqual(result["status"], AgentStatus.TASK_CANCELLED.value)
            self.assertEqual(calls, {"graceful": 1, "terminate": 0})
            self.assertEqual(json.loads((root / f"{task_id}.json").read_text(encoding="utf-8"))["state"], "CANCELLED")

    @unittest.skipUnless(os.name == "nt", "Windows cancellation terminal-race test")
    def test_graceful_action_preceding_nonzero_exit_finalization_classifies_cancelled(self):
        import runtime_agent.agent as agent
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); task_id = "failed-cancel-race"; token = "c" * 32
            record = {"schema_version": 1, "task_id": task_id, "state": "RUNNING", "pid": os.getpid() + 10_000_001,
                      "ownership_token": token, "boundary_type": "windows_job_object+process_group",
                      "job_name": "Local\\QSRuntime-" + token, "process_creation_time": "1235"}
            (root / f"{task_id}.json").write_text(json.dumps(record), encoding="utf-8")
            event = threading.Event(); calls = {"graceful": 0, "terminate": 0}
            class RacingJob:
                def __init__(self, *_args, **_kwargs): pass
                def active_processes(self): return 1
                def is_process_member(self, *_args): return True
                def send_ctrl_break(self, *_args, **_kwargs): calls["graceful"] += 1; event.set(); return True
                def terminate(self, *_args): calls["terminate"] += 1
                def close(self): pass
                def __enter__(self): return self
                def __exit__(self, *_args): self.close()
            def publish_failed():
                event.wait(2)
                with agent._task_record_lock(task_id, str(root)):
                    latest = agent._read_control(task_id, str(root))
                    action = agent._cancellation_action_evidence(
                        latest, ownership=token, request_id=str(latest.get("cancel_token", "")),
                        pid=int(latest["pid"]), creation_time=1235)
                    latest.update({"state": "CANCELLED" if action else "FAILED", "return_code": 9})
                    agent._atomic_json(agent._control_path(task_id, str(root)), latest)
            publisher = threading.Thread(target=publish_failed, daemon=True)
            with patch("runtime_agent.windows_job.WindowsJob", RacingJob), \
                    patch("runtime_agent.windows_job.process_exit_state", return_value=False):
                publisher.start()
                result = cancel_task(task_id, grace_seconds=.3, task_control_root=str(root))
                publisher.join(2)
                self.assertFalse(publisher.is_alive())
            final = json.loads((root / f"{task_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], AgentStatus.TASK_CANCELLED.value)
            self.assertEqual(final["state"], "CANCELLED")
            self.assertEqual(calls, {"graceful": 1, "terminate": 0})

    @unittest.skipUnless(os.name == "nt", "Windows process-group safety test")
    def test_group_zero_and_current_process_are_never_targeted(self):
        from runtime_agent.windows_job import WindowsJob
        with WindowsJob() as job:
            self.assertFalse(job.send_ctrl_break(0, 0, current_pid=os.getpid()))
            self.assertFalse(job.send_ctrl_break(os.getpid(), 0, current_pid=os.getpid()))

    @unittest.skipUnless(os.name == "nt", "Windows concurrent cancellation test")
    def test_concurrent_cancellation_requests_share_one_signal_sequence(self):
        from runtime_agent.windows_job import WindowsJob
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); engines, work, records = root / "engines", root / "workflows", root / "tasks"
            engines.mkdir(); cwd = work / "task"; cwd.mkdir(parents=True)
            fake = write_python_fixture(engines / "long_running.py", "import time\nwhile True: time.sleep(.05)\n")
            request = RuntimeProcessRequest("concurrent-cancel", RuntimePath(runtime_path(sys.executable)),
                                            (runtime_path(fake),), RuntimePath(runtime_path(cwd)), {})
            execution = []
            task_thread = threading.Thread(target=lambda: execution.append(execute_request(
                request, trusted_executable_roots=(runtime_path(Path(sys.executable).parent),),
                trusted_working_roots=(runtime_path(work),), task_control_root=str(records),
                enable_task_control=True)), daemon=True)
            original = WindowsJob.send_ctrl_break
            signals = []
            def counted(job, *args, **kwargs):
                signals.append(args[0])
                return original(job, *args, **kwargs)
            barrier = threading.Barrier(3)
            outputs = []
            def cancel():
                barrier.wait()
                outputs.append(cancel_task("concurrent-cancel", grace_seconds=.1, task_control_root=str(records)))
            callers = [threading.Thread(target=cancel, daemon=True) for _ in range(2)]
            with patch.object(WindowsJob, "send_ctrl_break", counted):
                task_thread.start()
                for _ in range(150):
                    if task_status("concurrent-cancel", task_control_root=str(records))["status"] == AgentStatus.TASK_RUNNING.value:
                        break
                    time.sleep(.02)
                for caller in callers: caller.start()
                barrier.wait()
                for caller in callers:
                    caller.join(8)
                    self.assertFalse(caller.is_alive())
                task_thread.join(5)
                self.assertFalse(task_thread.is_alive())
            self.assertEqual(len(signals), 1)
            self.assertEqual(len(outputs), 2)
            self.assertEqual(task_status("concurrent-cancel", task_control_root=str(records))["status"],
                             AgentStatus.TASK_CANCELLED.value)

    @unittest.skipUnless(os.name == "nt", "Windows startup cancellation test")
    def test_cancellation_during_startup_waits_for_verified_resume_transition(self):
        from runtime_agent.windows_job import WindowsJob
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); engines, work, records = root / "engines", root / "workflows", root / "tasks"
            engines.mkdir(); cwd = work / "task"; cwd.mkdir(parents=True)
            fake = write_python_fixture(engines / "startup.py", "import signal,time\nsignal.signal(signal.SIGBREAK, signal.SIG_IGN)\nwhile True: time.sleep(.05)\n")
            request = RuntimeProcessRequest("startup-cancel", RuntimePath(runtime_path(sys.executable)),
                                            (runtime_path(fake),), RuntimePath(runtime_path(cwd)), {})
            entered, release, caller_started = threading.Event(), threading.Event(), threading.Event()
            result, cancelled = [], []
            original = WindowsJob.resume_process
            def delayed_resume(job, process, creation):
                entered.set()
                if not release.wait(5): raise TimeoutError("synthetic resume gate timed out")
                return original(job, process, creation)
            execution = threading.Thread(target=lambda: result.append(execute_request(
                request, trusted_executable_roots=(runtime_path(Path(sys.executable).parent),),
                trusted_working_roots=(runtime_path(work),), task_control_root=str(records),
                enable_task_control=True)), daemon=True)
            def cancel_during_startup():
                caller_started.set()
                cancelled.append(cancel_task("startup-cancel", grace_seconds=.05, task_control_root=str(records)))
            caller = threading.Thread(target=cancel_during_startup, daemon=True)
            with patch.object(WindowsJob, "resume_process", delayed_resume):
                execution.start()
                self.assertTrue(entered.wait(5))
                caller.start()
                self.assertTrue(caller_started.wait(5))
                release.set()
                caller.join(8); execution.join(5)
            self.assertFalse(caller.is_alive())
            self.assertFalse(execution.is_alive())
            self.assertEqual(cancelled[0]["status"], AgentStatus.TASK_CANCELLED.value)
            self.assertEqual(task_status("startup-cancel", task_control_root=str(records))["status"],
                             AgentStatus.TASK_CANCELLED.value)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object ownership test")
    def test_windows_cancellation_removes_managed_tree_and_preserves_sentinel(self):
        from runtime_agent.windows_job import WindowsJob, process_creation_time, process_has_exited
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); engines, work, records = root / "engines", root / "workflows", root / "tasks"
            engines.mkdir(); cwd = work / "task"; cwd.mkdir(parents=True)
            marker = root / "grandchild.pid"
            script = write_python_fixture(engines / "tree.py", (
                "import subprocess,sys,time\n"
                "from pathlib import Path\n"
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'], shell=False)\n"
                f"Path({str(marker)!r}).write_text(str(child.pid))\n"
                "while True: time.sleep(.05)\n"))
            sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], shell=False)
            result = []
            request = RuntimeProcessRequest("owned-tree", RuntimePath(runtime_path(sys.executable)),
                                            (runtime_path(script),), RuntimePath(runtime_path(cwd)), {})
            thread = threading.Thread(target=lambda: result.append(execute_request(
                request, trusted_executable_roots=(runtime_path(Path(sys.executable).parent),),
                trusted_working_roots=(runtime_path(work),), task_control_root=str(records),
                enable_task_control=True)), daemon=True)
            try:
                thread.start()
                for _ in range(200):
                    if marker.exists() and (records / "owned-tree.json").exists(): break
                    time.sleep(.02)
                self.assertTrue(marker.exists(), "managed grandchild did not start")
                record = json.loads((records / "owned-tree.json").read_text(encoding="utf-8"))
                child_pid = int(marker.read_text(encoding="utf-8"))
                launch_creation = int(record["process_creation_time"])
                child_creation = process_creation_time(child_pid)
                with WindowsJob(str(record["job_name"]), create=False) as job:
                    self.assertGreaterEqual(job.active_processes(), 2)
                self.assertIsNone(sentinel.poll())
                cancelled = cancel_task("owned-tree", grace_seconds=.05, task_control_root=str(records))
                self.assertEqual(cancelled["status"], AgentStatus.TASK_CANCELLED.value)
                thread.join(5)
                self.assertFalse(thread.is_alive())
                for pid, creation in ((int(record["pid"]), launch_creation), (child_pid, child_creation)):
                    self.assertTrue(process_has_exited(pid, creation), "owned process remained live after cancellation")
                self.assertIsNone(sentinel.poll(), "unrelated sentinel was terminated")
                self.assertEqual(task_status("owned-tree", task_control_root=str(records))["status"],
                                 AgentStatus.TASK_CANCELLED.value)
            finally:
                if thread.is_alive():
                    cancel_task("owned-tree", grace_seconds=.05, task_control_root=str(records))
                    thread.join(5)
                if sentinel.poll() is None:
                    sentinel.terminate(); sentinel.wait(timeout=5)


class W5BoundaryTests(unittest.TestCase):
    def test_stage_models_preserve_generated_input_bytes_and_host_result_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); host = root / "host workflow"; host.mkdir(); generated = host / "scf.in"; generated.write_bytes(b"&CONTROL\n  prefix = 'Si'\n/\n")
            runtime = RuntimePath("/var/lib/quantumstudio/workflows/request/executions/e/task/scf.in")
            artifact = StageInArtifact(generated, runtime, ArtifactRole.INPUT, sha256=sha256_file(generated))
            self.assertEqual(artifact.host_source.read_bytes(), generated.read_bytes())
            out = StageOutArtifact(RuntimePath("/var/lib/quantumstudio/workflows/request/executions/e/task/scf.out"), host / "scf.out", ArtifactRole.PARSER_INPUT)
            self.assertEqual(out.host_destination.parent, host)
            self.assertFalse(str(out.host_destination).startswith("/var/lib/quantumstudio"))


class FixedAgentTransportTests(unittest.TestCase):
    class Runner:
        def __init__(self): self.calls = []
        def available(self): return True
        def run_with_input(self, arguments, input_data, *, timeout=None):
            self.calls.append((tuple(arguments), input_data))
            if arguments[-1] == "install-engine-pack":
                payload = json.loads(input_data.decode()); return WSLCommandResult(("wsl.exe", *arguments), 0, json.dumps({"status": "ACTIVATED", "manifest_sha256": payload["manifest_sha256"]}).encode())
            return WSLCommandResult(("wsl.exe", *arguments), 0, b'{"schema_version":1,"status":"TASK_CANCELLED","task_id":"task"}')
        def run_with_streaming_input(self, arguments, prefix, source_path, *, timeout=None):
            self.calls.append((tuple(arguments), prefix, Path(source_path).read_bytes()))
            header = json.loads(prefix.decode().splitlines()[0]); payload = {"schema_version": 1, "status": "TRANSFERRED", "sha256": header["sha256"]}
            return WSLCommandResult(("wsl.exe", *arguments), 0, json.dumps(payload).encode())
        def run_with_streaming_output(self, arguments, input_data, destination_path, *, timeout=None):
            self.calls.append((tuple(arguments), input_data)); Path(destination_path).write_bytes("runtime output Ω".encode())
            return WSLCommandResult(("wsl.exe", *arguments), 0)

    def test_transport_hard_binds_agent_distro_and_streams_binary_without_path_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "host input Ω"; source.write_bytes(b"input\x00data")
            runner = self.Runner(); transport = ManagedRuntimeArtifactTransport(runner)
            destination = RuntimePath("/var/lib/quantumstudio/workflows/w/executions/e/t/input")
            transport.stage_in(StageInArtifact(source, destination, ArtifactRole.INPUT, sha256=sha256_file(source)))
            host_destination = root / "host result Ω"; transport.stage_out(StageOutArtifact(destination, host_destination, ArtifactRole.PARSER_INPUT), host_root=root)
            self.assertEqual(host_destination.read_bytes(), "runtime output Ω".encode())
            self.assertEqual(runner.calls[0][0], ("--distribution", "QuantumStudioRuntime", "--exec", "/opt/quantumstudio/runtime/bin/qs-runtime-agent", "stage-in"))
            self.assertEqual(runner.calls[1][0], ("--distribution", "QuantumStudioRuntime", "--exec", "/opt/quantumstudio/runtime/bin/qs-runtime-agent", "stage-out"))
            self.assertNotIn("/mnt/c", str(runner.calls))
            self.assertNotIn("Ubuntu", str(runner.calls))
            source_pack = root / "pack"; make_pack(source_pack)
            deployment = ManagedEnginePackDeployment(transport)
            activated = deployment.install(EnginePackDescriptor("beta", source_pack, sha256_file(source_pack / "engine-pack.json")))
            self.assertEqual(activated["status"], "ACTIVATED")
            self.assertEqual(runner.calls[-1][0], ("--distribution", "QuantumStudioRuntime", "--exec", "/opt/quantumstudio/runtime/bin/qs-runtime-agent", "install-engine-pack"))


class EndToEndFakeScientificPipelineTests(unittest.TestCase):
    def test_fake_tool_stage_execute_collect_then_existing_result_service_uses_host_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); runtime_engines = root / "runtime engines"; runtime_work = root / "runtime workflows" / "w"; runtime_engines.mkdir(parents=True); runtime_work.mkdir(parents=True)
            tool = runtime_engines / "fake-bands"; bands_text = " &plot nbnd= 2, nks= 2 /\n 0 0 0\n -1.0 2.0\n 0 .5 0\n -0.5 2.5\n"
            tool = write_python_fixture(tool.with_suffix(".py"), "from pathlib import Path\nPath('bands.dat').write_text(%r)\nprint('JOB DONE')\n" % bands_text)
            host = root / "host workflow Ω"; task_dir = host / "bands"; task_dir.mkdir(parents=True); (task_dir / "generated.in").write_bytes(b"unchanged compiler bytes\n")
            runtime_input = runtime_work / "generated.in"; input_header = {"schema_version": 1, "operation": "stage_in", "destination": runtime_path(runtime_input), "sha256": sha256_file(task_dir / "generated.in")}
            with (task_dir / "generated.in").open("rb") as stream: stage_in(input_header, stream, trusted_roots=(runtime_path(runtime_work.parent),))
            request = RuntimeProcessRequest("fake-bands", RuntimePath(runtime_path(sys.executable)), (runtime_path(tool),), RuntimePath(runtime_path(runtime_work)), {}, RuntimePath(runtime_path(runtime_input)), RuntimePath(runtime_path(runtime_work / "bands.out")), RuntimePath(runtime_path(runtime_work / "bands.err")))
            process = execute_request(request, trusted_executable_roots=(runtime_path(Path(sys.executable).parent),), trusted_working_roots=(runtime_path(runtime_work.parent),))
            self.assertEqual(process.status, AgentStatus.PROCESS_EXITED); self.assertEqual(process.return_code, 0)
            for name in ("bands.dat", "bands.out"):
                with (task_dir / name).open("wb") as output:
                    stage_out({"schema_version": 1, "operation": "stage_out", "source": runtime_path(runtime_work / name)}, output, trusted_roots=(runtime_path(runtime_work.parent),))
            self.assertEqual((task_dir / "generated.in").read_bytes(), b"unchanged compiler bytes\n")
            (host / "manifest.json").write_text(json.dumps({"tasks": [{"task_id": "bands", "semantic_task_type": "qe_bands", "working_directory": "bands"}]}))
            record = WorkflowExecutionRecord("request", str(host), {"bands": TaskExecutionRecord("bands", state=TaskState.COMPLETED, stdout_path=str(task_dir / "bands.out"))}, execution_id="e")
            ExecutionStore(host).save(record)
            parsed = ResultService().parse(host, "e")
            self.assertEqual(len(parsed["parsed"]), 1)
            self.assertFalse(any("/runtime workflows/" in str(value) for value in [task_dir / "bands.dat", task_dir / "bands.out"]))
