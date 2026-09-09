import json, sys, tempfile, threading, time, unittest
from pathlib import Path
from backend.core.execution_contract import ArtifactLocality, CommandSpec, ExecutionMode
from backend.execution import GeneratedTask, GeneratedWorkflow, LocalExecutionManager, LocalExecutionService, LocalToolConfiguration, TaskState, WorkflowState, normalize_adapter_tasks
from backend.engines.qe.models import QETaskInput
from backend.execution.errors import ExecutionPreflightError

def workflow(root,tasks,external_artifacts=None):
    root=Path(root); root.mkdir(exist_ok=True)
    for task in tasks: (root/task.working_directory).mkdir(exist_ok=True)
    (root/"manifest.json").write_text(json.dumps({"request_id":"runtime-test","tasks":[x.task_id for x in tasks]}))
    return GeneratedWorkflow("runtime-test",root,tuple(tasks),external_artifacts=external_artifacts or {})
def task(name,deps=(),code="print('ok')",**kwargs):
    return GeneratedTask(name,name,"test_engine","python",name,CommandSpec(sys.executable,("-c",code),stdout_file="out.log",stderr_file="err.log"),tuple(deps),**kwargs)
def manager(callback=None): return LocalExecutionManager(LocalToolConfiguration(tool_paths={"python":sys.executable}),callback)

class QEConvergenceHandoffTests(unittest.TestCase):
 def test_nonconverged_qe_task_is_failed_and_blocks_postprocessor(self):
  with tempfile.TemporaryDirectory() as tmp:
   scf=GeneratedTask("scf","scf","quantum_espresso","python","scf",CommandSpec(sys.executable,("-c","print('convergence NOT achieved after 100 iterations: stopping')",),stdout_file="out.log",stderr_file="err.log"))
   post=GeneratedTask("proj","qe_projwfc","quantum_espresso","python","proj",CommandSpec(sys.executable,("-c","print('must not run')",),stdout_file="out.log",stderr_file="err.log"),dependencies=("scf",))
   result=manager().execute(workflow(tmp,(scf,post)))
   self.assertEqual(result.tasks["scf"].state,TaskState.FAILED)
   self.assertIn("convergence NOT achieved",result.tasks["scf"].error_message)
   self.assertEqual(result.tasks["proj"].state,TaskState.BLOCKED)

class ResourceFailureClassificationTests(unittest.TestCase):
 def test_qe_sigkill_with_memory_evidence_is_classified(self):
  with tempfile.TemporaryDirectory() as tmp:
   code="print(\"Estimated total dynamical RAM > 16.00 GB\", flush=True); import os,signal; os.kill(os.getpid(), signal.SIGKILL)"
   item=GeneratedTask("scf","scf","quantum_espresso","python","scf",CommandSpec(sys.executable,("-c",code),stdout_file="out.log",stderr_file="err.log"))
   result=manager().execute(workflow(tmp,(item,)))
   record=result.tasks["scf"]
   self.assertIn(record.return_code, (-9, 137, 1))
   self.assertEqual(record.error_type, "RESOURCE_OOM")
   self.assertIn("exceeded available memory", record.error_message)

class LocalExecutionTests(unittest.TestCase):
 def test_empty_workflow_is_not_successfully_finished(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); (root / "manifest.json").write_text(json.dumps({"request_id":"runtime-test","tasks":[]}))
   with self.assertRaisesRegex(ExecutionPreflightError, "no executable tasks"):
    manager().execute(GeneratedWorkflow("runtime-test", root, tuple()))

 def test_async_worker_propagates_preflight_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); (root / "manifest.json").write_text(json.dumps({"request_id":"runtime-test","tasks":[]}))
   handle=LocalExecutionService(manager()).start(GeneratedWorkflow("runtime-test", root, tuple()))
   self.assertTrue(handle.done.wait(3))
   self.assertIsNotNone(handle.error)
   self.assertIsNone(handle.result)
   self.assertIn("no executable tasks", str(handle.error))

 def test_simple_dependency_state_order_and_logs(self):
  with tempfile.TemporaryDirectory() as tmp:
   items=(task("a",code="print('A')"),task("b",("a",),"import os; print('B'); open('cwd.txt','w').write(os.getcwd())")); result=manager().execute(workflow(tmp,items)); self.assertEqual([result.tasks[x].state for x in ("a","b")],[TaskState.COMPLETED,TaskState.COMPLETED]); self.assertEqual(result.state,WorkflowState.COMPLETED); self.assertIn("A",Path(result.tasks["a"].stdout_path).read_text()); self.assertEqual(Path(tmp,"b","cwd.txt").read_text(),str(Path(tmp,"b").resolve()))
 def test_nonzero_blocks_downstream_and_branched_order_is_deterministic(self):
  with tempfile.TemporaryDirectory() as tmp:
   bad=(task("a",code="import sys; print('bad'); sys.exit(7)"),task("b",("a",))); result=manager().execute(workflow(tmp,bad)); self.assertEqual(result.tasks["a"].return_code,7); self.assertEqual(result.tasks["a"].state,TaskState.FAILED); self.assertIn("bad", result.tasks["a"].error_message); self.assertEqual(result.tasks["b"].state,TaskState.BLOCKED)
  with tempfile.TemporaryDirectory() as tmp:
   items=(task("a"),task("b",("a",)),task("c",("a",)),task("d",("b","c"))); result=manager().execute(workflow(tmp,items)); running=[x["task_id"] for x in result.events if x["state"]=="RUNNING"]; self.assertEqual(running,["a","b","c","d"])
 def test_stdin_stdout_stderr_timeout_and_cancellation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); item=GeneratedTask("io","io","test_engine","python","io",CommandSpec(sys.executable,("-c","import sys; print(sys.stdin.read()); print('err',file=sys.stderr)"),stdin_file="in.txt",stdout_file="out.log",stderr_file="err.log")); flow=workflow(root,(item,)); (root/"io"/"in.txt").write_text("input"); result=manager().execute(flow); self.assertIn("input",(root/"io"/"out.log").read_text()); self.assertIn("err",(root/"io"/"err.log").read_text())
  with tempfile.TemporaryDirectory() as tmp:
   item=task("slow",code="import time; time.sleep(2)",timeout_seconds=.1); result=manager().execute(workflow(tmp,(item,))); self.assertEqual(result.tasks["slow"].state,TaskState.FAILED); self.assertIn("timeout",result.tasks["slow"].error_message)
  with tempfile.TemporaryDirectory() as tmp:
   started=threading.Event(); item=task("cancel",code="import time; time.sleep(5)"); runner=manager(lambda event: started.set() if event["state"]=="RUNNING" else None); box={}; thread=threading.Thread(target=lambda:box.setdefault("result",runner.execute(workflow(tmp,(item,))))); thread.start(); self.assertTrue(started.wait(2)); runner.cancel(); thread.join(4); self.assertFalse(thread.is_alive()); self.assertEqual(box["result"].tasks["cancel"].state,TaskState.CANCELLED)
 def test_preflight_missing_tool_paths_external_artifact_and_modes(self):
  with tempfile.TemporaryDirectory() as tmp:
   flow=workflow(tmp,(GeneratedTask("bad","bad","test_engine","missing","bad",CommandSpec("missing-tool")),));
   with self.assertRaises(ExecutionPreflightError): manager().execute(flow)
  with tempfile.TemporaryDirectory() as tmp:
   item=task("external",artifact_inputs=("H",),artifact_locality={"H":ArtifactLocality.EXTERNAL});
   with self.assertRaises(ExecutionPreflightError): manager().execute(workflow(tmp,(item,)))
  with tempfile.TemporaryDirectory() as tmp:
   item=GeneratedTask("negf","negf","negf","negf","negf",CommandSpec("none",execution_mode=ExecutionMode.NOT_SELECTED));
   with self.assertRaises(ExecutionPreflightError): manager().execute(workflow(tmp,(item,)))
 def test_normalizes_adapter_boundary_and_async_service(self):
  with tempfile.TemporaryDirectory() as tmp:
   raw=QETaskInput("scf","scf","python","scf.in","scf.out","scf","print('ok')",metadata={"engine_id":"quantum_espresso","semantic_task_type":"scf"})
   root=Path(tmp); (root/"scf").mkdir(); (root/"scf"/"scf.in").write_text("print('ok')"); (root/"manifest.json").write_text(json.dumps({"request_id":"runtime-test"}))
   generated=normalize_adapter_tasks("runtime-test",root,(raw,))
   self.assertEqual(generated.tasks[0].command.stdin_file,"scf.in")
   service=LocalExecutionService(manager()); handle=service.start(generated); self.assertTrue(handle.done.wait(3)); self.assertIsNone(handle.error); self.assertEqual(handle.result.state,WorkflowState.COMPLETED)
 def test_tool_resolution_precedence_and_path_safety(self):
  config=LocalToolConfiguration(tool_paths={"python":sys.executable}); self.assertEqual(config.resolve("python","does-not-matter").resolve(),Path(sys.executable).resolve())
  with tempfile.TemporaryDirectory() as tmp:
   item=GeneratedTask("escape","escape","test_engine","python","../escape",CommandSpec(sys.executable));
   with self.assertRaises(ExecutionPreflightError): manager().execute(workflow(tmp,(item,)))
