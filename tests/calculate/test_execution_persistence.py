import json
import sys
import tempfile
import unittest
from pathlib import Path

from backend.core.execution_contract import CommandSpec
from backend.execution import (ExecutionStore, GeneratedTask, GeneratedWorkflow,
                               LocalExecutionManager, LocalToolConfiguration,
                               RecoveryState, TaskState)


def task(task_id, dependencies=(), code="print('ok')"):
    return GeneratedTask(task_id, task_id, "test", "python", task_id,
        CommandSpec(sys.executable, ("-c", code), stdout_file="out.log", stderr_file="err.log"), tuple(dependencies))


def workflow(root, tasks):
    root = Path(root)
    for item in tasks:
        (root / item.working_directory).mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps({"request_id": "request-a", "tasks": [item.task_id for item in tasks]}))
    return GeneratedWorkflow("request-a", root, tuple(tasks))


def manager():
    return LocalExecutionManager(LocalToolConfiguration(tool_paths={"python": sys.executable}))


class ExecutionPersistenceTests(unittest.TestCase):
    def test_roundtrip_stale_running_and_corrupt_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            flow = workflow(tmp, (task("a"),)); store = ExecutionStore(tmp); record = store.create(flow, request_fingerprint="request-fp")
            result = manager().execute(flow, record, store)
            loaded = store.assess(flow, request_id="request-a", request_fingerprint="request-fp")
            self.assertEqual(loaded.state, RecoveryState.COMPLETE); self.assertEqual(loaded.record.tasks["a"].attempt_count, 1)
            loaded.record.tasks["a"].state = TaskState.RUNNING; store.save(loaded.record)
            recovered = store.assess(flow); self.assertEqual(recovered.record.tasks["a"].state, TaskState.INTERRUPTED)
            sidecar = Path(tmp, "executions", recovered.record.execution_id, "execution.json"); sidecar.write_text("{")
            self.assertEqual(store.assess(flow).state, RecoveryState.CORRUPT_RUNTIME_RECORD)

    def test_resume_retry_preserves_attempt_logs_and_invalidates_downstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            flow = workflow(tmp, (task("a"), task("b", ("a",), "import sys; sys.exit(2)"), task("c", ("b",))))
            store = ExecutionStore(tmp); record = store.create(flow); first = manager().execute(flow, record, store)
            self.assertEqual(first.tasks["b"].state, TaskState.FAILED); first_log = first.tasks["b"].stdout_path
            flow.task_map()["b"].command.arguments  # immutable scientific identity remains unchanged
            replacement = GeneratedWorkflow("request-a", Path(tmp), (task("a"), task("b", ("a",)), task("c", ("b",))))
            resumed = manager().resume(replacement, first, store)
            self.assertEqual(resumed.tasks["a"].attempt_count, 1); self.assertEqual(resumed.tasks["b"].attempt_count, 2)
            self.assertTrue(Path(first_log).is_file()); self.assertEqual(resumed.tasks["c"].state, TaskState.COMPLETED)
            restarted = manager().restart_task(replacement, resumed, "a", store)
            self.assertEqual(restarted.tasks["a"].attempt_count, 2); self.assertEqual(restarted.tasks["b"].attempt_count, 3)

    def test_manifest_and_input_modification_are_not_resumable(self):
        with tempfile.TemporaryDirectory() as tmp:
            item = GeneratedTask("a", "a", "test", "python", "a", CommandSpec(sys.executable, ("-c", "print('ok')"), stdin_file="in.py"), input_files=("in.py",))
            flow = workflow(tmp, (item,)); Path(tmp, "a", "in.py").write_text("print('input')")
            store = ExecutionStore(tmp); store.create(flow)
            Path(tmp, "a", "in.py").write_text("print('changed')")
            self.assertEqual(store.assess(flow).state, RecoveryState.INCOMPATIBLE)
            Path(tmp, "manifest.json").write_text(json.dumps({"request_id": "request-a", "changed": True}))
            self.assertEqual(store.assess(flow).state, RecoveryState.INCOMPATIBLE)

    def test_restart_workflow_creates_independent_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            flow = workflow(tmp, (task("a"),)); store = ExecutionStore(tmp)
            one = store.create(flow); manager().execute(flow, one, store)
            two = store.create(flow); manager().execute(flow, two, store)
            self.assertNotEqual(one.execution_id, two.execution_id); self.assertEqual(len(store.list()), 2)

