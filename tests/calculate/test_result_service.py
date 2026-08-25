import tempfile, unittest
from pathlib import Path
from backend.execution import ExecutionStore
from backend.results import DEFAULT_PARSERS, ResultStore
from frontend.services.result_service import ResultService

class ResultServiceTests(unittest.TestCase):
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
