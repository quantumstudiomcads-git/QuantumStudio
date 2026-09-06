import json, tempfile, unittest
from unittest.mock import patch
import numpy as np
from pathlib import Path
from backend.execution import ExecutionStore
from backend.execution.models import WorkflowExecutionRecord, TaskExecutionRecord, TaskState
from backend.results import DEFAULT_PARSERS, ResultStore, ResultProvenance, ResultStatus, ScientificResult
from frontend.services.result_service import ResultService

class ResultServiceTests(unittest.TestCase):
 def test_real_qe_bands_filband_is_structured_and_idempotent(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); task=root/"003_qe_bands"; task.mkdir(); source=task/"bands.dat"; source.write_text(" &plot nbnd= 2, nks= 2 /\n 0 0 0\n -1.0 2.0\n 0 .5 0\n -0.5 2.5\n"); (root/"manifest.json").write_text('{"tasks":[{"task_id":"bands-task","semantic_task_type":"qe_bands","working_directory":"003_qe_bands"}]}'); output=task/"bands.out"; output.write_text("JOB DONE"); record=WorkflowExecutionRecord("request",str(root),{"bands-task":TaskExecutionRecord("bands-task",state=TaskState.COMPLETED,stdout_path=str(output))},execution_id="e"); ExecutionStore(root).save(record)
   service=ResultService(); first=service.parse(root,"e"); second=service.parse(root,"e"); self.assertEqual(len(first["parsed"]),1); self.assertEqual(first["parsed"],second["parsed"]); result=service.load_result(root,"e",first["parsed"][0]); self.assertEqual(result.arrays["energies"].shape,(2,2)); self.assertEqual(len(service.summaries(root,"e")),1)
 def test_e2_dos_and_pdos_completed_artifacts_parse_and_recover(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); dos=root/"003_qe_dos"; pdos=root/"005_qe_projwfc"; dos.mkdir(); pdos.mkdir()
   (dos/"dos.dat").write_text("# E dos Int dos EFermi = 2 eV\n-1 1 0\n0 2 1\n"); (pdos/"sample.pdos_atm#1(Si)_wfc#1(s)").write_text("# E ldos pdos\n-1 0 1\n0 1 2\n")
   (root/"manifest.json").write_text("{\"tasks\":[{\"task_id\":\"dos\",\"semantic_task_type\":\"qe_dos\",\"working_directory\":\"003_qe_dos\",\"dependencies\":[\"nscf\"],\"metadata\":{\"task_metadata\":{\"purpose\":\"dos\"}}},{\"task_id\":\"pdos\",\"semantic_task_type\":\"qe_projwfc\",\"working_directory\":\"005_qe_projwfc\",\"dependencies\":[\"nscf-pdos\"],\"metadata\":{\"task_metadata\":{\"purpose\":\"pdos\"}}}]}")
   record=WorkflowExecutionRecord("request",str(root),{"dos":TaskExecutionRecord("dos",state=TaskState.COMPLETED,stdout_path=str(dos/"dos.out")),"pdos":TaskExecutionRecord("pdos",state=TaskState.COMPLETED,stdout_path=str(pdos/"projwfc.out"))},execution_id="e"); (dos/"dos.out").write_text("JOB DONE"); (pdos/"projwfc.out").write_text("JOB DONE"); ExecutionStore(root).save(record)
   parsed=ResultService().parse(root,"e"); self.assertEqual(len(parsed["parsed"]),2); rows=parsed["rows"]; self.assertEqual({row["type"] for row in rows},{"DOSResult","PDOSResult"})
   result=ResultService().load_result(root,"e",next(row["result_id"] for row in rows if row["type"]=="PDOSResult")); self.assertEqual(result.metadata["workflow_provenance"]["purpose"],"pdos")

 def test_e2_completed_dos_inherits_nonconverged_parent_scf_status(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); scf=root/"001_scf"; dos=root/"003_qe_dos"; scf.mkdir(); dos.mkdir()
   (scf/"scf.out").write_text("! total energy = -1 Ry\nJOB DONE.\n")
   (dos/"dos.dat").write_text("# E dos\n-1 1\n0 2\n")
   (root/"manifest.json").write_text("{\"tasks\":[{\"task_id\":\"scf\",\"calculation_id\":\"scf\",\"semantic_task_type\":\"scf\",\"working_directory\":\"001_scf\"},{\"task_id\":\"dos\",\"semantic_task_type\":\"qe_dos\",\"working_directory\":\"003_qe_dos\",\"dependencies\":[\"scf\"]}]}")
   record=WorkflowExecutionRecord("request",str(root),{"scf":TaskExecutionRecord("scf",state=TaskState.COMPLETED,stdout_path=str(scf/"scf.out")),"dos":TaskExecutionRecord("dos",state=TaskState.COMPLETED,stdout_path=str(dos/"dos.out"))},execution_id="e"); (dos/"dos.out").write_text("JOB DONE"); ExecutionStore(root).save(record)
   rows=ResultService().parse(root,"e")["rows"]
   self.assertEqual(next(row["status"] for row in rows if row["type"]=="DOSResult"),"NOT_CONVERGED")

 def test_e2_pdos_uses_only_parent_scf_fermi_metadata_when_available(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); scf=root/"001_scf"; pdos=root/"005_qe_projwfc"; scf.mkdir(); pdos.mkdir()
   (scf/"scf.out").write_text("! total energy = -1 Ry\nthe Fermi energy is 2.5 eV\nconvergence has been achieved\nJOB DONE.\n")
   (pdos/"sample.pdos_atm#1(Si)_wfc#1(s)").write_text("# E ldos pdos\n-1 0 1\n0 1 2\n")
   (root/"manifest.json").write_text("{\"tasks\":[{\"task_id\":\"scf\",\"calculation_id\":\"scf\",\"semantic_task_type\":\"scf\",\"working_directory\":\"001_scf\"},{\"task_id\":\"pdos\",\"semantic_task_type\":\"qe_projwfc\",\"working_directory\":\"005_qe_projwfc\",\"dependencies\":[\"scf\"]}]}")
   (pdos/"projwfc.out").write_text("JOB DONE")
   record=WorkflowExecutionRecord("request",str(root),{"scf":TaskExecutionRecord("scf",state=TaskState.COMPLETED,stdout_path=str(scf/"scf.out")),"pdos":TaskExecutionRecord("pdos",state=TaskState.COMPLETED,stdout_path=str(pdos/"projwfc.out"))},execution_id="e"); ExecutionStore(root).save(record)
   rows=ResultService().parse(root,"e")["rows"]; result=ResultService().load_result(root,"e",next(row["result_id"] for row in rows if row["type"]=="PDOSResult"))
   self.assertEqual(result.metadata["fermi_energy_eV"],2.5); self.assertEqual(result.metadata["fermi_reference"]["source_task"],"scf")

 def test_raman_final_dynmat_uses_parent_ph_tensor_and_parses_once(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); scf=root/"001_scf"; parent=root/"002_raman"; final=root/"003_qe_dynmat_raman"; scf.mkdir(); parent.mkdir(); final.mkdir()
   (scf/"scf.in").write_text("ecutwfc = 40\necutrho = 160\nK_POINTS automatic\n12 12 12 0 0 0\n")
   (parent/"raman.in").write_text("eth_rps=1e-9\neth_ns=1e-12\ndek=1e-3\ntr2_ph=1e-12\n")
   (final/"dynmat.in").write_text("asr='crystal'\n")
   parent_out=parent/"raman.out.attempt001"; parent_out.write_text("PARENT RAMAN TENSORS")
   final_source=final/"raman.dynmat.out"; final_source.write_text("FINAL MODES")
   final_out=final/"dynmat.out.attempt001"; final_out.write_text("FINAL ACTIVITIES")
   manifest={"tasks":[
    {"task_id":"scf","semantic_task_type":"scf","working_directory":"001_scf","input_filename":"scf.in"},
    {"task_id":"raman","semantic_task_type":"raman","working_directory":"002_raman","input_filename":"raman.in","dependencies":["scf"]},
    {"task_id":"dynmat","calculation_id":"qe_dynmat_raman","semantic_task_type":"qe_dynmat","working_directory":"003_qe_dynmat_raman","input_filename":"dynmat.in","dependencies":["raman"],"metadata":{"pseudopotentials":{"Si":{"sha256":"digest"}},"task_metadata":{"purpose":"raman","parent_raman_task_id":"raman","expected_mode_count":6}}}
   ]}
   (root/"manifest.json").write_text(json.dumps(manifest))
   record=WorkflowExecutionRecord("request",str(root),{
    "raman":TaskExecutionRecord("raman",state=TaskState.COMPLETED,stdout_path=str(parent_out)),
    "dynmat":TaskExecutionRecord("dynmat",state=TaskState.COMPLETED,stdout_path=str(final_out))},execution_id="e")
   ExecutionStore(root).save(record); calls=[]
   def parse(route,source,**kwargs):
    calls.append((route,Path(source),kwargs))
    provenance=ResultProvenance("request","e","dynmat","quantum_espresso","ph.x",[str(source)],{},"qe.ph.raman")
    return ScientificResult("RamanResult",ResultStatus.VALID,provenance,arrays={"frequencies_cm1":np.zeros(6),"frequencies_THz":np.zeros(6),"raman_activity":np.zeros(6),"depolarization_ratio":np.zeros(6),"raman_tensors":np.zeros((6,3,3)),"raman_active_mask":np.zeros(6,dtype=bool)})
   with patch("frontend.services.result_service.DEFAULT_PARSERS.parse",side_effect=parse): outcome=ResultService().parse(root,"e")
   self.assertEqual(outcome["errors"],())
   self.assertEqual(len(calls),1)
   self.assertEqual(calls[0][0],"QE_RAMAN")
   self.assertEqual(calls[0][1],final_source)
   self.assertEqual(calls[0][2]["raman_tensor_text"],"PARENT RAMAN TENSORS")
   self.assertEqual(calls[0][2]["activity_text"],"FINAL ACTIVITIES")
   self.assertEqual(calls[0][2]["tool_id"],"dynmat.x")
   self.assertEqual(calls[0][2]["pseudopotentials"]["Si"]["sha256"],"digest")
   self.assertEqual(calls[0][2]["calculation_settings"]["kpoints"]["mesh"],[12,12,12])
   self.assertEqual(calls[0][2]["calculation_settings"]["ecutwfc"],40.0)
   self.assertEqual(calls[0][2]["calculation_settings"]["eth_rps"],1e-9)
   self.assertEqual(calls[0][2]["calculation_settings"]["asr"],"crystal")

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
