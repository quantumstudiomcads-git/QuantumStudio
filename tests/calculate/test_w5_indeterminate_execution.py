"""Managed execution must respect the agent's durable task-control outcome."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.core.execution_contract import ExecutionMode
from backend.execution.models import TaskState, WorkflowState
from backend.runtime.managed_science import (ManagedScientificExecutionService,
                                             ManagedTaskControlError)
from runtime_agent.protocol import AgentStatus, RuntimePath, RuntimeProcessResult


class _Runtime:
    def __init__(self, return_code):
        self.return_code = return_code
        self.launches = 0

    def _require_execution_ready(self):
        return SimpleNamespace(capabilities={"run", "stage_in", "stage_out", "status", "cancel"})

    def runtime_provenance(self):
        return {}

    def execute_runtime_task(self, request, record=None):
        self.launches += 1
        return SimpleNamespace(process=RuntimeProcessResult(
            request.task_id, AgentStatus.PROCESS_EXITED, True, True, self.return_code, 12345),
            diagnostic="")


class _Transport:
    def __init__(self, payload):
        self.payload = payload

    def stage_out(self, *args, **kwargs):
        pass

    def task_status(self, task_id):
        return self.payload


class ManagedIndeterminateExecutionTests(unittest.TestCase):
    def _fixture(self, root, return_code, status, *, state=None, failure_code=None):
        command = SimpleNamespace(execution_mode=ExecutionMode.SUBPROCESS, program="tool",
                                  arguments=(), environment={}, stdin_file=None,
                                  stdout_file=None, stderr_file=None)
        task = SimpleNamespace(task_id="task", dependencies=(), command=command, tool_id="tool",
                               engine_id="synthetic", input_files=(), artifact_outputs=(),
                               working_directory="task", timeout_seconds=None)
        workflow = SimpleNamespace(root=str(root), request_id="request", tasks=(task,))
        runtime = _Runtime(return_code)
        engine = SimpleNamespace(resolve=lambda tool_id: RuntimePath("/opt/quantumstudio/engines/tool"))
        payload = {"schema_version": 1, "status": status, "task_id": "task",
                   "failure_code": failure_code,
                   "record": {"task_id": "task", "state": state or status.removeprefix("TASK_"),
                              "return_code": return_code, "failure_code": failure_code}}
        service = ManagedScientificExecutionService(runtime, engine, _Transport(payload))
        return workflow, runtime, service

    def test_code_zero_and_nonzero_indeterminate_remain_terminal(self):
        for code in (0, 7):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                workflow, runtime, service = self._fixture(
                    Path(tmp), code, "TASK_CANCELLATION_INDETERMINATE",
                    failure_code="cancellation_action_outcome_unproven")
                parsed = []
                result = service.execute(workflow,
                    result_service=SimpleNamespace(parse=lambda *args: parsed.append(args)))
                task = result.tasks["task"]
                self.assertEqual((task.state, result.state),
                                 (TaskState.INDETERMINATE, WorkflowState.INDETERMINATE))
                self.assertEqual((task.error_type, task.return_code),
                                 ("cancellation_action_outcome_unproven", code))
                self.assertIn("operator review", task.error_message)
                self.assertEqual(parsed, [])
                self.assertEqual(service.recover_running("task"),
                    {"state": "INDETERMINATE", "failure_code": "cancellation_action_outcome_unproven",
                     "return_code": code, "diagnostic": "Operator review is required before any new attempt."})
                with self.assertRaises(ManagedTaskControlError): service.execute(workflow, record=result)
                self.assertEqual(runtime.launches, 1)

    def test_authoritative_outcomes_take_precedence_over_return_code(self):
        cases = (
            (0, "TASK_CANCELLED", "CANCELLED", TaskState.CANCELLED),
            (0, "TASK_FINISHED", "FINISHED", TaskState.COMPLETED),
            (7, "TASK_FINISHED", "FINISHED", TaskState.FAILED),
            (0, "TASK_OUTCOME_INDETERMINATE", "OUTCOME_INDETERMINATE", TaskState.INDETERMINATE),
            (0, "UNKNOWN_FUTURE_STATE", "UNKNOWN", TaskState.INDETERMINATE),
        )
        for code, status, agent_state, expected in cases:
            with self.subTest(status=status, code=code), tempfile.TemporaryDirectory() as tmp:
                workflow, runtime, service = self._fixture(Path(tmp), code, status, state=agent_state)
                record = service.execute(workflow)
                self.assertEqual(record.tasks["task"].state, expected)
                self.assertEqual(runtime.launches, 1)
                if status == "UNKNOWN_FUTURE_STATE":
                    self.assertEqual(service.recover_running("task")["state"], "INDETERMINATE")

    def test_artifact_collection_failure_cannot_erase_indeterminate_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflow, runtime, service = self._fixture(
                Path(tmp), 0, "TASK_CANCELLATION_INDETERMINATE",
                failure_code="cancellation_action_outcome_unproven")
            def fail_stage(*args, **kwargs): raise OSError("synthetic stage-out failure")
            service.transport.stage_out = fail_stage
            record = service.execute(workflow)
            self.assertEqual(record.tasks["task"].state, TaskState.INDETERMINATE)
            self.assertEqual(record.tasks["task"].error_type, "cancellation_action_outcome_unproven")

    def test_launch_persistence_failure_cannot_adopt_a_previous_task_outcome(self):
        for status in ("TASK_FINISHED", "TASK_RUNNING", "TASK_CANCELLED"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                workflow, runtime, service = self._fixture(Path(tmp), 0, status)
                def execute(request, record=None):
                    runtime.launches += 1
                    return SimpleNamespace(process=RuntimeProcessResult(
                        request.task_id, AgentStatus.TASK_CONTROL_PERSISTENCE_FAILED,
                        True, False, None, None), diagnostic="")
                runtime.execute_runtime_task = execute
                parsed = []
                result = service.execute(workflow,
                    result_service=SimpleNamespace(parse=lambda *args: parsed.append(args)))
                task = result.tasks["task"]
                self.assertEqual(task.state, TaskState.INDETERMINATE)
                self.assertEqual(task.error_type, "task_control_persistence_failed")
                self.assertIsNone(task.return_code)
                self.assertEqual(parsed, [])
                with self.assertRaises(ManagedTaskControlError):
                    service.execute(workflow, record=result)
                self.assertEqual(runtime.launches, 1)
