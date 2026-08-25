"""Qt-free Calculate-facing access to C8 execution-sidecar Results."""
from __future__ import annotations
import json
from pathlib import Path
from backend.execution import ExecutionStore
from backend.execution.models import TaskState
from backend.results import DEFAULT_PARSERS, ResultStore, ResultStoreError, ResultParseError


class ResultService:
 def load_result(self, workflow_root, execution_id, result_id):
  store=ResultStore(workflow_root, execution_id); result=store.load(result_id); result.status=store.validate_sources(result); return result
 def executions(self, workflow_root): return ExecutionStore(workflow_root).list()
 def execution_record(self, workflow_root, execution_id): return ExecutionStore(workflow_root).load(execution_id)
 def summaries(self, workflow_root, execution_id):
  store=ResultStore(workflow_root,execution_id); rows=[]
  for result_id in store.list():
   try:
    result=store.load(result_id); status=store.validate_sources(result)
    rows.append({"result_id":result_id,"type":result.result_type,"status":status.value,"summary":result.summary(),"provenance":result.provenance})
   except ResultStoreError as error: rows.append({"result_id":result_id,"type":"Unreadable Result","status":"PARSE_FAILED","summary":str(error),"provenance":None})
  return tuple(rows)

 def _manifest(self, root):
  path=Path(root).resolve()/"manifest.json"
  try: data=json.loads(path.read_text(encoding="utf-8"))
  except (OSError,json.JSONDecodeError) as error: raise ResultStoreError("Generated workflow manifest is missing or invalid.") from error
  return {str(item.get("task_id")):item for item in data.get("tasks",()) if isinstance(item,dict)}

 def _source(self, root, task, runtime, semantic):
  """Pick only the completed task's current attempt output or bounded raw contract."""
  workflow=Path(root).resolve(); directory=(workflow/str(task.get("working_directory",""))).resolve()
  if workflow not in directory.parents and directory != workflow: raise ResultStoreError("Task directory escapes generated workflow root.")
  names={"qe_bands":("bands.dat",), "qe_dos":("dos.dat",), "qe_matdyn":("phdos.dat","phonon.dos"), "qe_projwfc":("pdos_atm#",)}
  for name in names.get(semantic,()):
   if name.endswith("#"):
    candidates=sorted(directory.glob(name+"*"))
    if candidates and all(directory in candidate.resolve().parents for candidate in candidates): return directory
   else:
    candidate=(directory/name).resolve()
    if candidate.is_file() and directory in candidate.parents: return candidate
  if runtime.stdout_path:
   output=Path(runtime.stdout_path).resolve()
   if output.is_file() and workflow in output.parents: return output
  return None

 def parse(self, workflow_root, execution_id, *, reparse=False):
  """Parse terminal task artifacts for one C7 attempt without running engines."""
  root=Path(workflow_root).resolve(); record=ExecutionStore(root).load(execution_id); manifest=self._manifest(root); store=ResultStore(root,execution_id)
  parsed=[]; errors=[]
  routes={"scf":"QE_SCF_STDOUT","relax":"QE_RELAX_STDOUT","vc_relax":"QE_RELAX_STDOUT","qe_bands":"BAND_STRUCTURE_RAW_DATA","qe_dos":"DOS_RAW_DATA","qe_matdyn":"PHONON_DOS_RAW_DATA","qe_projwfc":"PDOS_RAW_DATA","wannier90_run":"WANNIER_WOUT","epw":"EPW_SUMMARY"}
  for task_id,runtime in record.tasks.items():
   if runtime.state is not TaskState.COMPLETED: continue
   task=manifest.get(task_id,{}) ; semantic=str(task.get("semantic_task_type", "")); route=routes.get(semantic)
   if route is None: continue
   source=self._source(root,task,runtime,semantic)
   if source is None:
    errors.append(f"{semantic}: declared result source is missing."); continue
   try:
    result=DEFAULT_PARSERS.parse(route,source,request_id=record.request_id,execution_id=execution_id,task_id=task_id)
    if reparse or result.result_id not in store.list(): store.save(result)
    parsed.append(result.result_id)
   except (ResultParseError,ResultStoreError,ValueError) as error:
    errors.append(f"{semantic}: {error}")
  return {"parsed":tuple(parsed),"errors":tuple(errors),"rows":self.summaries(root,execution_id)}
