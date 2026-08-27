"""Serial, dependency-aware local executor for generic GeneratedWorkflow contracts."""
from __future__ import annotations
import json, os, signal, subprocess, threading, time
from pathlib import Path
from backend.core.execution_contract import ArtifactLocality, ExecutionMode
from backend.pseudopotentials.models import sha256
from .errors import ArtifactUnavailableError, ExecutionPreflightError, UnsupportedExecutionModeError
from .models import TaskExecutionRecord, TaskState, WorkflowExecutionRecord, now
from .tools import LocalToolConfiguration

def _failure_tail(stderr_path, stdout_path):
 for path in (stderr_path, stdout_path):
  try: text=Path(path).read_text(encoding="utf-8",errors="replace").strip()
  except OSError: continue
  if text: return "\n".join(text.splitlines()[-12:])
 return ""


class LocalExecutionManager:
 def __init__(self,tools=None,event_callback=None): self.tools=tools or LocalToolConfiguration(); self.event_callback=event_callback; self._cancel=threading.Event(); self._process=None; self._lock=threading.Lock(); self._store=None
 def _emit(self,record,task_id,state):
  entry={"task_id":task_id,"state":state.value,"timestamp":now()}; record.events.append(entry)
  if self._store: self._store.save(record)
  if self.event_callback:self.event_callback(entry)
 def _safe(self,root,directory,relative):
  result=(root/directory/relative).resolve()
  if root not in result.parents and result!=root: raise ExecutionPreflightError("Execution path escapes generated workflow root.")
  return result
 def preflight(self,workflow):
  root=Path(workflow.root).resolve(); errors=[]; task_map=workflow.task_map()
  if not root.is_dir(): errors.append("Generated workflow root does not exist.")
  manifest=root/workflow.manifest_filename
  try:
   data=json.loads(manifest.read_text(encoding="utf-8"));
   if not isinstance(data,dict): errors.append("Generated workflow manifest is invalid.")
   elif data.get("request_id") not in (None, workflow.request_id): errors.append("Generated workflow manifest does not match the selected request.")
  except Exception: errors.append("Generated workflow manifest is missing or invalid.")
  else:
   materials=data.get("materialized_pseudopotentials")
   if data.get("pseudopotentials") and not materials:
    for element, pseudo in (data.get("pseudopotentials") or {}).items():
     if isinstance(pseudo,dict) and pseudo.get("sha256") and pseudo.get("source") and Path(str(pseudo["source"])).is_file() and sha256(pseudo["source"]) != pseudo["sha256"]:
      errors.append(f"Pseudopotential {element!r}: SHA-256 no longer matches generated provenance.")
    errors.append("Generated pseudopotentials were not materialized. Regenerate the QE inputs.")
   elif materials is not None and not isinstance(materials,dict):
    errors.append("Generated pseudopotential manifest is invalid.")
   elif materials:
    for element, pseudo in materials.items():
     if not isinstance(pseudo,dict):
      errors.append(f"Generated pseudopotential manifest is invalid for {element!r}."); continue
     filename=str(pseudo.get("filename", "")).strip(); relative=str(pseudo.get("relative_path", "")).strip()
     target=(root/relative).resolve()
     if not filename or not relative or root not in target.parents:
      errors.append(f"Generated pseudopotential manifest is invalid for {element!r}."); continue
     if not target.is_file() or not os.access(target,os.R_OK):
      errors.append(f"Generated pseudopotential file is missing: {filename}"); continue
     expected=pseudo.get("sha256")
     if expected and sha256(target)!=expected:
      errors.append(f"Generated pseudopotential SHA-256 does not match manifest: {filename}")
  if int(self.tools.cpu_cores) < 1: errors.append("Local CPU cores must be at least 1.")
  if int(self.tools.omp_threads) < 1: errors.append("OpenMP threads must be at least 1.")
  for task in workflow.tasks:
   if any(dep not in task_map for dep in task.dependencies): errors.append(f"{task.task_id}: unknown dependency.")
   directory=self._safe(root,"",task.working_directory)
   if not directory.is_dir(): errors.append(f"{task.task_id}: working directory is missing.")
   for filename in task.input_files:
    if not self._safe(root,task.working_directory,filename).is_file(): errors.append(f"{task.task_id}: required input {filename!r} is missing.")
   mode=task.command.execution_mode
   if mode is ExecutionMode.SUBPROCESS:
    try:self.tools.resolve(task.tool_id,task.command.program,task.engine_id)
    except ExecutionPreflightError as error:errors.append(f"{task.task_id}: {error}")
   elif mode is not ExecutionMode.PYTHON_API: errors.append(f"{task.task_id}: execution backend is not selected or supported.")
   else: errors.append(f"{task.task_id}: Python API binding is not registered.")
   for artifact in task.artifact_inputs:
    if task.artifact_locality.get(artifact) is ArtifactLocality.EXTERNAL and artifact not in workflow.external_artifacts: errors.append(f"{task.task_id}: external artifact {artifact!r} is unavailable.")
  return tuple(errors)
 def _terminate_current(self):
  with self._lock: process=self._process
  if process and process.poll() is None:
   try:
    if os.name=="posix": os.killpg(os.getpgid(process.pid),signal.SIGTERM)
    else: process.terminate()
    try: process.wait(timeout=1)
    except subprocess.TimeoutExpired:
     if os.name=="posix": os.killpg(os.getpgid(process.pid),signal.SIGKILL)
     else: process.kill()
   except ProcessLookupError: pass
 def cancel(self):
  self._cancel.set(); self._terminate_current()
 def _run_task(self,workflow,task,record):
  root=Path(workflow.root).resolve(); runtime=record.tasks[task.task_id]; runtime.attempt_count += 1; runtime.state=TaskState.RUNNING; runtime.started_at=now(); runtime.timeout_seconds=task.timeout_seconds; self._emit(record,task.task_id,runtime.state)
  directory=self._safe(root,"",task.working_directory); command=task.command; executable=self.tools.resolve(task.tool_id,command.program,task.engine_id); runtime.resolved_executable=str(executable)
  argv=[str(executable),*command.arguments]
  if int(self.tools.cpu_cores)>1 and self.tools.mpi_capable(task.tool_id):
   launcher=self.tools.resolved_mpi_launcher(); flag,count=self.tools.mpi_arguments(launcher,self.tools.cpu_cores); argv=[str(launcher),flag,count,*argv]
  stdin=self._safe(root,task.working_directory,command.stdin_file).open("rb") if command.stdin_file else None
  stdout_name=command.stdout_file or "stdout.log"; stderr_name=command.stderr_file or "stderr.log"
  if record.execution_id:
   stdout_name=f"{stdout_name}.attempt{runtime.attempt_count:03d}"; stderr_name=f"{stderr_name}.attempt{runtime.attempt_count:03d}"
  stdout_path=self._safe(root,task.working_directory,stdout_name); stderr_path=self._safe(root,task.working_directory,stderr_name); runtime.stdout_path=str(stdout_path); runtime.stderr_path=str(stderr_path)
  try:
   with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
    env=os.environ.copy(); env.update(self.tools.environment); env.update(command.environment); env["OMP_NUM_THREADS"]=str(int(self.tools.omp_threads))
    process=subprocess.Popen(argv,cwd=directory,stdin=stdin,stdout=stdout,stderr=stderr,env=env,shell=False,start_new_session=(os.name=="posix"))
    with self._lock:self._process=process
    started=time.monotonic()
    while process.poll() is None:
     if self._cancel.is_set(): self._terminate_current(); runtime.state=TaskState.CANCELLED; runtime.error_message="Cancelled by user."; break
     if task.timeout_seconds and time.monotonic()-started>task.timeout_seconds:
      self._terminate_current(); runtime.state=TaskState.FAILED; runtime.error_message="Task timeout exceeded."; break
     time.sleep(.03)
    runtime.return_code=process.poll()
    if runtime.state is TaskState.RUNNING: runtime.state=TaskState.COMPLETED if runtime.return_code==0 else TaskState.FAILED
    if runtime.state is TaskState.FAILED and not runtime.error_message:
     stdout.flush(); stderr.flush(); detail=_failure_tail(stderr_path,stdout_path)
     runtime.error_message=f"Process exited with code {runtime.return_code}." + (("\n" + detail) if detail else "")
  finally:
   if stdin:stdin.close()
   with self._lock:self._process=None
   runtime.finished_at=now(); self._emit(record,task.task_id,runtime.state)
 def execute(self,workflow, record=None, store=None):
  errors=self.preflight(workflow)
  if errors: raise ExecutionPreflightError("\n".join(errors))
  self._cancel.clear(); self._store=store; records=record.tasks if record is not None else {task.task_id:TaskExecutionRecord(task.task_id) for task in workflow.tasks}; record=record or WorkflowExecutionRecord(workflow.request_id,str(Path(workflow.root).resolve()),records); record.started_at=record.started_at or now(); task_map=workflow.task_map()
  for task in workflow.tasks:
   runtime=records[task.task_id]
   if runtime.state is TaskState.COMPLETED: continue
   dependencies=[records[item].state for item in task.dependencies]
   if any(state in {TaskState.FAILED,TaskState.CANCELLED,TaskState.BLOCKED} for state in dependencies): runtime.state=TaskState.BLOCKED; runtime.error_message="Blocked by prerequisite."; runtime.finished_at=now(); self._emit(record,task.task_id,runtime.state); continue
   if self._cancel.is_set(): runtime.state=TaskState.CANCELLED; runtime.finished_at=now(); self._emit(record,task.task_id,runtime.state); continue
   runtime.state=TaskState.READY; self._emit(record,task.task_id,runtime.state); self._run_task(workflow,task,record)
  record.finished_at=now();
  if self._store: self._store.save(record)
  return record

 def resume(self, workflow, record, store=None):
  retryable={TaskState.FAILED, TaskState.INTERRUPTED, TaskState.CANCELLED}
  first=next((task.task_id for task in workflow.tasks if record.tasks[task.task_id].state in retryable), None)
  if first is not None:
   descendants = store.invalidate_downstream(workflow, record, first) if store else {first}
   for task_id in descendants: record.tasks[task_id].state=TaskState.PENDING
  return self.execute(workflow, record, store)

 def restart_task(self, workflow, record, task_id, store=None):
  if record.tasks[task_id].state is TaskState.RUNNING: raise ExecutionPreflightError("Cannot restart a running task.")
  descendants = store.invalidate_downstream(workflow, record, task_id) if store else {task_id}
  for item in descendants: record.tasks[item].state=TaskState.PENDING
  return self.execute(workflow, record, store)
