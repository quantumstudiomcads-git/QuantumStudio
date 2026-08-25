"""Machine-local tool and resource configuration; never CalculationRequest state."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import os, shutil
from .errors import ExecutableNotFoundError

MPI_CAPABLE_TOOLS=frozenset({"pw.x","ph.x","bands.x","dos.x","projwfc.x","pp.x","q2r.x","matdyn.x","pw2wannier90.x","wannier90.x","epw.x"})

def available_logical_cpus():
 try:
  affinity=os.sched_getaffinity(0)
  if affinity:return max(1,len(affinity))
 except (AttributeError,OSError): pass
 return max(1,int(os.cpu_count() or 1))

@dataclass
class LocalToolConfiguration:
 tool_paths:dict[str,str]=field(default_factory=dict); engine_directories:dict[str,str]=field(default_factory=dict); environment:dict[str,str]=field(default_factory=dict)
 cpu_cores:int=1; omp_threads:int=1; mpi_launcher:str="auto"
 def resolve(self,tool_id,program,engine_id=None):
  candidates=[]
  if tool_id in self.tool_paths:candidates.append(Path(self.tool_paths[tool_id]))
  if engine_id and engine_id in self.engine_directories:candidates.append(Path(self.engine_directories[engine_id])/program)
  found=shutil.which(program,path=self.environment.get("PATH") or os.environ.get("PATH"))
  if found:candidates.append(Path(found))
  for candidate in candidates:
   if candidate.is_file() and os.access(candidate,os.X_OK): return candidate.resolve()
  raise ExecutableNotFoundError(f"Local executable for {tool_id!r} ({program!r}) is not configured or executable.")
 def mpi_capable(self,tool_id): return tool_id in MPI_CAPABLE_TOOLS
 def resolved_mpi_launcher(self):
  requested=str(self.mpi_launcher or "auto")
  if requested.lower()!="auto":
   path=Path(requested)
   if path.is_file() and os.access(path,os.X_OK): return path.resolve()
   raise ExecutableNotFoundError("Configured MPI launcher is not executable.")
  for program in ("mpirun","mpiexec"):
   found=shutil.which(program,path=self.environment.get("PATH") or os.environ.get("PATH"))
   if found:
    path=Path(found)
    if path.is_file() and os.access(path,os.X_OK): return path.resolve()
  raise ExecutableNotFoundError("No MPI launcher was found. Configure MPI in Local Tools or select 1 core.")
 def mpi_arguments(self,launcher,cores): return ("-n" if Path(launcher).name.lower().startswith("mpiexec") else "-np",str(int(cores)))
