import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import unittest

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
            fake = write_python_fixture(engines / "long_running.py", "import os,signal,time\nif os.name != 'nt':\n signal.signal(signal.SIGTERM, signal.SIG_IGN)\nwhile True:\n time.sleep(.05)\n")
            request = RuntimeProcessRequest("owned-task", RuntimePath(runtime_path(sys.executable)), (runtime_path(fake),), RuntimePath(runtime_path(cwd)), {})
            result = []
            thread = threading.Thread(target=lambda: result.append(execute_request(request, trusted_executable_roots=(runtime_path(Path(sys.executable).parent),), trusted_working_roots=(runtime_path(work),), task_control_root=str(records), enable_task_control=True)), daemon=True)
            thread.start()
            for _ in range(100):
                if task_status("owned-task", task_control_root=str(records))["status"] == AgentStatus.TASK_RUNNING.value: break
                time.sleep(.02)
            self.assertEqual(task_status("owned-task", task_control_root=str(records))["status"], AgentStatus.TASK_RUNNING.value)
            cancelled = cancel_task("owned-task", grace_seconds=.05, task_control_root=str(records))
            self.assertEqual(cancelled["status"], AgentStatus.TASK_CANCELLED.value)
            self.assertEqual(cancelled["outcome"], "KILLED_AFTER_GRACE")
            thread.join(3); self.assertFalse(thread.is_alive())
            allowed_codes = (-9, None, 15) if os.name == "nt" else (-9, None)
            self.assertIn(result[0].return_code, allowed_codes); self.assertIn(result[0].status, {AgentStatus.PROCESS_EXITED, AgentStatus.INTERNAL_AGENT_ERROR})
            self.assertEqual(task_status("owned-task", task_control_root=str(records))["status"], AgentStatus.TASK_CANCELLED.value)
            with self.assertRaises(Exception): cancel_task("../not-a-task", task_control_root=str(records))


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
