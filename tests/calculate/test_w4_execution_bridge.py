import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from backend.execution import ManagedWSL2Runtime, TaskExecutionRecord, WorkflowExecutionRecord, select_compute_runtime
from backend.execution.errors import ExecutionPreflightError
from backend.runtime import (
    MANAGED_DISTRO_NAME, ManagedRuntimeExecutionBridge, ManagedRuntimeHealthState,
    OperatingSystem, RuntimeBridgeError, RuntimeBridgeHealth, WSLCommandResult,
    WSLDiscovery, agent_argv, detect_platform,
)
from runtime_agent.agent import execute_request
from runtime_agent.protocol import AgentStatus, ProtocolError, RuntimePath, RuntimeProcessRequest, RuntimeProcessResult
from tests.helpers.fake_executable import runtime_path, write_python_fixture

WINDOWS = detect_platform(system="Windows", machine="AMD64", python_bits=64)
LINUX = detect_platform(system="Linux", machine="x86_64", python_bits=64)
LIST_HEADER = b"NAME STATE VERSION\n"


class DiscoveryRunner:
    def __init__(self, version=2, available=True):
        self.version, self.available_value, self.calls = version, available, []
    def available(self):
        return self.available_value
    def run(self, arguments):
        args = tuple(arguments); self.calls.append(args)
        if args == ("--list", "--verbose"):
            body = f"{MANAGED_DISTRO_NAME} Stopped {self.version}\n".encode()
            return WSLCommandResult(("wsl.exe", *args), returncode=0, stdout=LIST_HEADER + body)
        if args == ("--version",):
            return WSLCommandResult(("wsl.exe", *args), returncode=0, stdout=b"WSL version: 2\n")
        return WSLCommandResult(("wsl.exe", *args), returncode=1)


class AgentRunner:
    def __init__(self, *, available=True, health=None, process=None, error=None, returncode=0):
        self.available_value, self.health, self.process = available, health, process
        self.error, self.returncode, self.calls = error, returncode, []
    def available(self):
        return self.available_value
    def run_with_input(self, arguments, input_data, *, timeout=None):
        args = tuple(arguments); self.calls.append((args, input_data, timeout))
        if args[-1] == "health":
            payload = self.health or {"schema_version": 1, "agent_version": "1", "status": "READY"}
        else:
            payload = self.process
        return WSLCommandResult(("wsl.exe", *args), returncode=self.returncode,
                                stdout=json.dumps(payload).encode() if payload is not None else b"",
                                error=self.error)


def runtime_request(root, *, exit_code=0):
    executable_root = Path(root) / "engines"
    working_root = Path(root) / "workflows"
    cwd = working_root / "job space"
    executable_root.mkdir(); cwd.mkdir(parents=True)
    fake = write_python_fixture(executable_root / "fake-engine.py", "import json, os, sys\nprint(json.dumps({'argv':sys.argv[1:], 'cwd':os.getcwd(), 'env':os.environ.get('QS_TEST_VALUE'), 'stdin':sys.stdin.buffer.read().decode('utf-8')}))\nprint('deterministic stderr', file=sys.stderr)\nsys.exit(int(os.environ.get('QS_EXIT_CODE', '0')))\n")
    stdin, stdout, stderr = cwd / "input.in", cwd / "output.out", cwd / "output.err"
    stdin.write_bytes(b"input with Unicode \xce\xa9\n")
    request = RuntimeProcessRequest("task ü", RuntimePath(runtime_path(sys.executable)), (runtime_path(fake), "space value", "Ω", "", "--flag=value"),
                                    RuntimePath(runtime_path(cwd)), {"QS_TEST_VALUE": "hello world", "QS_EXIT_CODE": str(exit_code)},
                                    RuntimePath(runtime_path(stdin)), RuntimePath(runtime_path(stdout)), RuntimePath(runtime_path(stderr)))
    return request, Path(sys.executable).parent, working_root, stdout, stderr


class RuntimeProtocolAndAgentTests(unittest.TestCase):
    def test_runtime_path_and_protocol_validation_reject_host_paths_and_bad_environment(self):
        with self.assertRaises(ProtocolError): RuntimePath("C:\\\\Users\\\\Alice")
        with self.assertRaises(ProtocolError): RuntimePath("relative/path")
        with self.assertRaises(ProtocolError): RuntimePath("/safe\x00bad")
        with self.assertRaises(ProtocolError):
            RuntimeProcessRequest("t", RuntimePath("/opt/quantumstudio/engines/x"), (), RuntimePath("/var/lib/quantumstudio/workflows/x"), {"BAD-KEY": "x"})
        with self.assertRaises(ProtocolError): RuntimeProcessRequest.from_json('{"schema_version": 99}')

    def test_agent_health_runs_as_normal_local_process(self):
        result = subprocess.run([sys.executable, "-m", "runtime_agent.agent", "health"], capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "READY")

    def test_agent_preserves_argv_environment_io_exit_code_and_process_group(self):
        for exit_code in (0, 1, 42):
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory(prefix="runtime Ω ") as root:
                request, executable_root, working_root, stdout, stderr = runtime_request(root, exit_code=exit_code)
                result = execute_request(request, trusted_executable_roots=(runtime_path(executable_root),), trusted_working_roots=(runtime_path(working_root),))
                self.assertEqual(result.status, AgentStatus.PROCESS_EXITED)
                self.assertEqual(result.return_code, exit_code)
                self.assertTrue(result.started and result.finished)
                self.assertEqual(result.runtime_pid, result.runtime_process_group)
                observed = json.loads(stdout.read_text())
                self.assertEqual(observed["argv"], ["space value", "\u03a9", "", "--flag=value"])
                # RuntimePath is the POSIX wire representation.  On native
                # Windows the agent launches the fixture through a host-side
                # wrapper, so the child reports the resolved host path.
                self.assertEqual(Path(observed["cwd"]).resolve(), Path(str(request.cwd)).resolve())
                self.assertEqual(observed["env"], "hello world")
                self.assertEqual(observed["stdin"].encode("utf-8"), b"input with Unicode \xce\xa9\n")
                self.assertEqual(stderr.read_text(), "deterministic stderr\n")

    def test_agent_rejects_untrusted_executable_cwd_and_missing_stdin(self):
        with tempfile.TemporaryDirectory() as root:
            request, executable_root, working_root, _, _ = runtime_request(root)
            rejected = RuntimeProcessRequest(request.task_id, RuntimePath("/bin/echo"), (), request.cwd, {})
            self.assertEqual(execute_request(rejected, trusted_executable_roots=(runtime_path(executable_root),), trusted_working_roots=(runtime_path(working_root),)).status, AgentStatus.EXECUTABLE_REJECTED)
            rejected_cwd = RuntimeProcessRequest(request.task_id, request.executable, (), RuntimePath("/etc"), {})
            self.assertEqual(execute_request(rejected_cwd, trusted_executable_roots=(runtime_path(executable_root),), trusted_working_roots=(runtime_path(working_root),)).status, AgentStatus.CWD_REJECTED)
            missing = RuntimeProcessRequest(request.task_id, request.executable, (), request.cwd, {}, RuntimePath(runtime_path(working_root / "missing.in")))
            self.assertEqual(execute_request(missing, trusted_executable_roots=(runtime_path(executable_root),), trusted_working_roots=(runtime_path(working_root),)).status, AgentStatus.STDIN_MISSING)
            if os.name != "nt":
                escaped = executable_root / "escaped-engine"
                escaped.symlink_to("/bin/echo")
                symlinked = RuntimeProcessRequest(request.task_id, RuntimePath(runtime_path(escaped)), (), request.cwd, {})
                self.assertEqual(execute_request(symlinked, trusted_executable_roots=(runtime_path(executable_root),), trusted_working_roots=(runtime_path(working_root),)).status, AgentStatus.EXECUTABLE_REJECTED)


class ManagedBridgeTests(unittest.TestCase):
    def _request(self):
        return RuntimeProcessRequest("task 量子", RuntimePath("/opt/quantumstudio/engines/fake"), ("space value", "Ω", "", "--x=y"), RuntimePath("/var/lib/quantumstudio/workflows/a"), {"OMP_NUM_THREADS": "2"})

    def test_transport_uses_fixed_managed_distro_json_stdin_and_preserves_nonzero_exit(self):
        request = self._request()
        response = RuntimeProcessResult(request.task_id, AgentStatus.PROCESS_EXITED, True, True, 42, 123, 123).to_dict()
        runner = AgentRunner(process=response)
        bridge = ManagedRuntimeExecutionBridge(runner)
        result = bridge.execute(request)
        self.assertTrue(result.completed)
        self.assertEqual(result.process.return_code, 42)
        args, payload, timeout = runner.calls[0]
        self.assertEqual(args, ("--distribution", MANAGED_DISTRO_NAME, "--exec", "/opt/quantumstudio/runtime/bin/qs-runtime-agent", "run"))
        self.assertIsNone(timeout)
        self.assertEqual(RuntimeProcessRequest.from_json(payload), request)
        self.assertNotIn("Ubuntu", str(args))

    def test_agent_health_and_malformed_response_are_controlled(self):
        good = ManagedRuntimeExecutionBridge(AgentRunner())
        self.assertTrue(good.probe_agent().ready)
        malformed = ManagedRuntimeExecutionBridge(AgentRunner(health={"bad": "payload"}))
        self.assertEqual(malformed.probe_agent().error, RuntimeBridgeError.AGENT_PROTOCOL_ERROR)
        incompatible = ManagedRuntimeExecutionBridge(AgentRunner(health={"schema_version": 1, "agent_version": "99", "status": "READY"}))
        self.assertEqual(incompatible.probe_agent().error, RuntimeBridgeError.AGENT_UNAVAILABLE)
        request = self._request()
        broken = ManagedRuntimeExecutionBridge(AgentRunner(process={"schema_version": 1}))
        self.assertEqual(broken.execute(request).error, RuntimeBridgeError.AGENT_PROTOCOL_ERROR)

    def test_user_distro_substitution_is_structurally_impossible(self):
        request = self._request()
        runner = AgentRunner(process=RuntimeProcessResult(request.task_id, AgentStatus.PROCESS_EXITED, True, True, 0).to_dict())
        self.assertTrue(ManagedRuntimeExecutionBridge(runner).execute(request).completed)
        self.assertEqual(runner.calls[0][0][1], MANAGED_DISTRO_NAME)
        with self.assertRaises(ValueError):
            agent_argv("Ubuntu")


class ManagedProviderReadinessTests(unittest.TestCase):
    def _report(self, version=2):
        return WSLDiscovery(DiscoveryRunner(version), WINDOWS).probe()

    def test_runtime_requires_windows_wsl2_metadata_and_agent_health(self):
        bridge = ManagedRuntimeExecutionBridge(AgentRunner())
        cases = [
            ManagedWSL2Runtime(LINUX, self._report(), ManagedRuntimeHealthState.METADATA_VALID, bridge),
            ManagedWSL2Runtime(WINDOWS, self._report(1), ManagedRuntimeHealthState.METADATA_VALID, bridge),
            ManagedWSL2Runtime(WINDOWS, self._report(), ManagedRuntimeHealthState.METADATA_INVALID, bridge),
            ManagedWSL2Runtime(WINDOWS, self._report(), ManagedRuntimeHealthState.METADATA_VALID, bridge, RuntimeBridgeHealth(False)),
        ]
        for runtime in cases:
            with self.subTest(runtime=runtime.info.operating_system):
                self.assertEqual(runtime.probe().state.value, "AVAILABLE_NOT_READY" if runtime.info.operating_system is OperatingSystem.WINDOWS else "INVALID")
                with self.assertRaises(ExecutionPreflightError): runtime.execute_runtime_task(ManagedBridgeTests()._request())

    def test_runtime_executes_runtime_local_task_and_records_backward_compatible_provenance(self):
        request = ManagedBridgeTests()._request()
        response = RuntimeProcessResult(request.task_id, AgentStatus.PROCESS_EXITED, True, True, 0, 100, 100).to_dict()
        runtime = ManagedWSL2Runtime(WINDOWS, self._report(), ManagedRuntimeHealthState.METADATA_VALID,
                                     ManagedRuntimeExecutionBridge(AgentRunner(process=response)), RuntimeBridgeHealth(True, "1", 1),
                                     runtime_version="0.2-runtime.1", architecture="x86_64")
        record = WorkflowExecutionRecord("r", "/tmp", {"t": TaskExecutionRecord("t")})
        result = runtime.execute_runtime_task(request, record=record)
        self.assertTrue(result.completed)
        self.assertEqual(record.provider_provenance["runtime_id"], MANAGED_DISTRO_NAME)
        self.assertEqual(record.provider_provenance["agent_protocol_schema"], 1)
        with self.assertRaises(ExecutionPreflightError): runtime.execute(None)
        selected = select_compute_runtime(info=WINDOWS, health_report=self._report(),
                                          provisioning_health=ManagedRuntimeHealthState.METADATA_VALID,
                                          agent_bridge=runtime.agent_bridge, agent_health=RuntimeBridgeHealth(True, "1", 1))
        self.assertIsInstance(selected, ManagedWSL2Runtime)


if __name__ == "__main__":
    unittest.main()
