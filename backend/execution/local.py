"""Serial, dependency-aware local executor for generic GeneratedWorkflow contracts."""
from __future__ import annotations
import json, os, signal, subprocess, threading, time
from pathlib import Path
from backend.core.execution_contract import ArtifactLocality, ExecutionMode
from backend.pseudopotentials.models import sha256
from .errors import ArtifactUnavailableError, ExecutionPreflightError, UnsupportedExecutionModeError
from .models import TaskExecutionRecord, TaskState, WorkflowExecutionRecord, now
from .tools import LocalToolConfiguration
from .diagnostics import extract_qe_failure
from .artifacts import ArtifactError, ArtifactRegistry, ArtifactResolver, RequiredArtifactMissing

def _validate_qgrid_artifacts(directory, metadata):
 """Validate the QE 7.6 ldisp dyn0/indexed set before q2r consumes it."""
 directory=Path(directory); prefix=str(metadata.get("qe_prefix") or "").strip()
 candidates=sorted(directory.glob(prefix + ".dyn*") if prefix else directory.glob("*.dyn*"))
 grid=directory / (prefix + ".dyn0") if prefix else next((item for item in candidates if item.name.endswith("0")), directory / "dynamical-matrix0")
 if not grid.is_file() or grid.stat().st_size == 0: return "Uniform-q phonon metadata dyn0 is missing or empty."
 try: lines=grid.read_text(encoding="utf-8",errors="replace").splitlines(); first=[int(value) for value in lines[0].split()[:3]]; expected=int(lines[1].split()[0])
 except (ValueError,IndexError,OSError): return "Uniform-q phonon dyn0 metadata is malformed."
 requested=metadata.get("qmesh")
 if requested is not None and list(first) != [int(value) for value in requested]: return "Uniform-q phonon dyn0 q-mesh does not match the declared producer identity."
 if expected < 1: return "Uniform-q phonon dyn0 declares no irreducible q points."
 indexed=[directory / (grid.name[:-1] + str(index)) for index in range(1, expected + 1)]
 missing=[item.name for item in indexed if not item.is_file() or item.stat().st_size == 0]
 if missing: return "Uniform-q phonon dynamical set is incomplete: missing " + ", ".join(missing)
 if any("q = (" not in item.read_text(encoding="utf-8",errors="replace") for item in indexed): return "Uniform-q phonon dynamical set contains a file without q-point data."
 return None

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
  if not workflow.tasks: errors.append("Workflow contains no executable tasks.")
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
  try: ArtifactResolver(workflow, ArtifactRegistry(root, "validation")).validate()
  except ArtifactError as error: errors.append(str(error))
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
  root=Path(workflow.root).resolve(); runtime=record.tasks[task.task_id]; directory=self._safe(root,"",task.working_directory)
  try: ArtifactResolver(workflow, ArtifactRegistry(root, record.execution_id)).materialize(task)
  except (ArtifactError, RequiredArtifactMissing) as error:
   runtime.state=TaskState.FAILED; runtime.error_type="PREPARATION_ARTIFACT_MISSING"; runtime.error_message=str(error); runtime.finished_at=now(); self._emit(record,task.task_id,runtime.state); return
  runtime.attempt_count += 1; runtime.state=TaskState.RUNNING; runtime.started_at=now(); runtime.timeout_seconds=task.timeout_seconds; self._emit(record,task.task_id,runtime.state)
  command=task.command; executable=self.tools.resolve(task.tool_id,command.program,task.engine_id); runtime.resolved_executable=str(executable)
  argv=[str(executable),*command.arguments]
  launcher_path=None
  actual_ranks=1
  if int(self.tools.cpu_cores)>1 and self.tools.mpi_capable(task.tool_id):
   launcher_path=self.tools.resolved_mpi_launcher(); flag,count=self.tools.mpi_arguments(launcher_path,self.tools.cpu_cores); argv=[str(launcher_path),flag,count,*argv]; actual_ranks=int(self.tools.cpu_cores)
   if task.tool_id == "epw.x" and actual_ranks > 1:
    argv.extend(("-npool", str(actual_ranks)))
  runtime.requested_cores=int(self.tools.cpu_cores)
  runtime.actual_mpi_ranks=actual_ranks
  runtime.omp_threads_per_rank=int(self.tools.omp_threads)
  runtime.mpi_launcher=str(launcher_path) if launcher_path is not None else None
  runtime.command_argv=list(argv)
  runtime.engine_version=str(task.metadata.get("backend_version") or self.tools.qe_version or "") or None
  stdin=self._safe(root,task.working_directory,command.stdin_file).open("rb") if command.stdin_file else None
  stdout_name=command.stdout_file or "stdout.log"; stderr_name=command.stderr_file or "stderr.log"
  if record.execution_id:
   stdout_name=f"{stdout_name}.attempt{runtime.attempt_count:03d}"; stderr_name=f"{stderr_name}.attempt{runtime.attempt_count:03d}"
  stdout_path=self._safe(root,task.working_directory,stdout_name); stderr_path=self._safe(root,task.working_directory,stderr_name); runtime.stdout_path=str(stdout_path); runtime.stderr_path=str(stderr_path)
  try:
   with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
    env=os.environ.copy(); env.update(self.tools.environment); env.update(command.environment); env["OMP_NUM_THREADS"]=str(int(self.tools.omp_threads))
    process=subprocess.Popen(argv,cwd=directory,stdin=stdin,stdout=stdout,stderr=stderr,env=env,shell=False,start_new_session=(os.name=="posix"))
    runtime.process_id=process.pid
    if self._store: self._store.save(record)
    with self._lock:self._process=process
    started=time.monotonic()
    while process.poll() is None:
     if self._cancel.is_set(): self._terminate_current(); runtime.state=TaskState.CANCELLED; runtime.error_message="Cancelled by user."; break
     if task.timeout_seconds and time.monotonic()-started>task.timeout_seconds:
      self._terminate_current(); runtime.state=TaskState.FAILED; runtime.error_message="Task timeout exceeded."; break
     time.sleep(.03)
    runtime.return_code=process.poll()
    if runtime.state is TaskState.RUNNING:
     runtime.state=TaskState.COMPLETED if runtime.return_code==0 else TaskState.FAILED
    # QE can return zero after writing only config/charge-density when an SCF
    # stops at electron_maxstep.  Such a state is not a valid restart input for
    # projwfc.x or other wavefunction consumers, so classify it as failed before
    # dependency scheduling can launch a postprocessor.
    if runtime.state is TaskState.COMPLETED and task.engine_id == "quantum_espresso":
     if task.semantic_task_type == "qe_ph" and (task.metadata.get("task_metadata", {}) or {}).get("purpose") == "harmonic_qmesh":
      problem = _validate_qgrid_artifacts(directory, task.metadata)
      if problem:
       runtime.state=TaskState.FAILED; runtime.error_message=problem
     try:
      stdout_text=stdout_path.read_text(encoding="utf-8", errors="replace")
      stderr_text=stderr_path.read_text(encoding="utf-8", errors="replace")
     except OSError:
      stdout_text=stderr_text=""
     if "convergence NOT achieved" in stdout_text:
      runtime.state=TaskState.FAILED
      runtime.error_message=extract_qe_failure(stdout_text, stderr_text, runtime.return_code) or "Quantum ESPRESSO SCF did not converge; restart wavefunctions were not produced."
    if runtime.state is TaskState.COMPLETED:
     try: ArtifactRegistry(root, record.execution_id).register(task, ArtifactResolver.declarations(task))
     except RequiredArtifactMissing as error:
      runtime.state=TaskState.FAILED; runtime.error_type="REQUIRED_ARTIFACT_MISSING"; runtime.error_message=str(error)
    if runtime.state is TaskState.FAILED and not runtime.error_message:
     stdout.flush(); stderr.flush()
     try:
      stdout_text=stdout_path.read_text(encoding="utf-8", errors="replace")
      stderr_text=stderr_path.read_text(encoding="utf-8", errors="replace")
     except OSError:
      stdout_text=stderr_text=""
     detail=extract_qe_failure(stdout_text, stderr_text, runtime.return_code)
     oom_signal = runtime.return_code in {137, -9}
     oom_evidence = oom_signal and any(token.lower() in (stdout_text + "\n" + stderr_text).lower() for token in ("estimated total dynamical ram", "estimated max dynamical ram", "out of memory", "oom", "cannot allocate"))
     if oom_evidence:
      runtime.error_type="RESOURCE_OOM"
      runtime.error_message="Process was terminated by the operating system, most likely because the calculation exceeded available memory. " + (detail or f"Process exited with code {runtime.return_code}.")
     else:
      runtime.error_message=detail or f"Process exited with code {runtime.return_code}."
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

 def reconcile_completed_artifacts(self, workflow, record):
  """Register declared outputs of completed compatible tasks without rerunning them."""
  registry=ArtifactRegistry(workflow.root, record.execution_id)
  for task in workflow.tasks:
   if record.tasks[task.task_id].state is TaskState.COMPLETED:
    registry.register(task, ArtifactResolver.declarations(task))
  return registry.load()
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
