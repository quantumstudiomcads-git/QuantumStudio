import tempfile, unittest
from pathlib import Path
from backend.execution import ExecutionStore
from backend.execution.models import WorkflowExecutionRecord, TaskExecutionRecord, TaskState
from backend.results import DEFAULT_PARSERS, ResultStore
from frontend.services.result_service import ResultService

class ResultServiceTests(unittest.TestCase):
 def test_real_qe_bands_filband_is_structured_and_idempotent(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); task=root/"003_qe_bands"; task.mkdir(); source=task/"bands.dat"; source.write_text(" &plot nbnd= 2, nks= 2 /\n 0 0 0\n -1.0 2.0\n 0 .5 0\n -0.5 2.5\n"); (root/"manifest.json").write_text('{"tasks":[{"task_id":"bands-task","semantic_task_type":"qe_bands","working_directory":"003_qe_bands"}]}'); output=task/"bands.out"; output.write_text("JOB DONE"); record=WorkflowExecutionRecord("request",str(root),{"bands-task":TaskExecutionRecord("bands-task",state=TaskState.COMPLETED,stdout_path=str(output))},execution_id="e"); ExecutionStore(root).save(record)
   service=ResultService(); first=service.parse(root,"e"); second=service.parse(root,"e"); self.assertEqual(len(first["parsed"]),1); self.assertEqual(first["parsed"],second["parsed"]); result=service.load_result(root,"e",first["parsed"][0]); self.assertEqual(result.arrays["energies"].shape,(2,2)); self.assertEqual(len(service.summaries(root,"e")),1)
 def test_stored_metadata_is_listed_without_qt_parser_access(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); (root/"manifest.json").write_text('{"request_id":"r"}')
   # C7 sidecar directory is intentionally discovered independently of project state.
   execution="e"; source=root/"scf.out"; source.write_text("! total energy = -1 Ry\nconvergence has been achieved\n")
   result=DEFAULT_PARSERS.parse("QE_SCF_STDOUT",source,request_id="r",execution_id=execution,task_id="scf")
   store=ResultStore(root,execution); store.save(result)
   # Result service tolerates execution histories created by C7; create its sidecar marker.
   (root/"executions"/execution).mkdir(exist_ok=True); (root/"executions"/execution/"execution.json").write_text("{}")
   rows=ResultService().summaries(root,execution); self.assertEqual(rows[0]["type"],"GroundStateResult"); self.assertEqual(rows[0]["status"],"VALID")
