"""Serial, dependency-aware local executor for generic GeneratedWorkflow contracts."""
from __future__ import annotations
import json, os, signal, subprocess, threading, time
from pathlib import Path
from backend.core.execution_contract import ArtifactLocality, ExecutionMode
from .errors import ArtifactUnavailableError, ExecutionPreflightError, UnsupportedExecutionModeError
from .models import TaskExecutionRecord, TaskState, WorkflowExecutionRecord, now
from .tools import LocalToolConfiguration

class LocalExecutionManager:
 def __init__(self,tools=None,event_callback=None): self.tools=tools or LocalToolConfiguration(); self.event_callback=event_callback; self._cancel=threading.Event(); self._process=None; self._lock=threading.Lock()
 def _emit(self,record,task_id,state):
  entry={"task_id":task_id,"state":state.value,"timestamp":now()}; record.events.append(entry)
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
  root=Path(workflow.root).resolve(); runtime=record.tasks[task.task_id]; runtime.state=TaskState.RUNNING; runtime.started_at=now(); self._emit(record,task.task_id,runtime.state)
  directory=self._safe(root,"",task.working_directory); command=task.command; executable=self.tools.resolve(task.tool_id,command.program,task.engine_id)
  stdin=self._safe(root,task.working_directory,command.stdin_file).open("rb") if command.stdin_file else None
  stdout_path=self._safe(root,task.working_directory,command.stdout_file or "stdout.log"); stderr_path=self._safe(root,task.working_directory,command.stderr_file or "stderr.log"); runtime.stdout_path=str(stdout_path); runtime.stderr_path=str(stderr_path)
  try:
   with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
    env=os.environ.copy(); env.update(self.tools.environment); env.update(command.environment)
    process=subprocess.Popen([str(executable),*command.arguments],cwd=directory,stdin=stdin,stdout=stdout,stderr=stderr,env=env,shell=False,start_new_session=(os.name=="posix"))
    with self._lock:self._process=process
    started=time.monotonic()
    while process.poll() is None:
     if self._cancel.is_set(): self._terminate_current(); runtime.state=TaskState.CANCELLED; runtime.error_message="Cancelled by user."; break
     if task.timeout_seconds and time.monotonic()-started>task.timeout_seconds:
      self._terminate_current(); runtime.state=TaskState.FAILED; runtime.error_message="Task timeout exceeded."; break
     time.sleep(.03)
    runtime.return_code=process.poll()
    if runtime.state is TaskState.RUNNING: runtime.state=TaskState.COMPLETED if runtime.return_code==0 else TaskState.FAILED
    if runtime.state is TaskState.FAILED and not runtime.error_message: runtime.error_message=f"Process exited with code {runtime.return_code}."
  finally:
   if stdin:stdin.close()
   with self._lock:self._process=None
   runtime.finished_at=now(); self._emit(record,task.task_id,runtime.state)
 def execute(self,workflow):
  errors=self.preflight(workflow)
  if errors: raise ExecutionPreflightError("\n".join(errors))
  self._cancel.clear(); records={task.task_id:TaskExecutionRecord(task.task_id) for task in workflow.tasks}; record=WorkflowExecutionRecord(workflow.request_id,str(Path(workflow.root).resolve()),records); task_map=workflow.task_map()
  for task in workflow.tasks:
   runtime=records[task.task_id]
   dependencies=[records[item].state for item in task.dependencies]
   if any(state in {TaskState.FAILED,TaskState.CANCELLED,TaskState.BLOCKED} for state in dependencies): runtime.state=TaskState.BLOCKED; runtime.error_message="Blocked by prerequisite."; runtime.finished_at=now(); self._emit(record,task.task_id,runtime.state); continue
   if self._cancel.is_set(): runtime.state=TaskState.CANCELLED; runtime.finished_at=now(); self._emit(record,task.task_id,runtime.state); continue
   runtime.state=TaskState.READY; self._emit(record,task.task_id,runtime.state); self._run_task(workflow,task,record)
  return record
