"""Machine-local tool and resource configuration; never CalculationRequest state."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json, os, shutil
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
 cpu_cores:int=1; omp_threads:int=1; mpi_launcher:str="auto"; qe_bin_directory:str=""; qe_version:str=""

 @staticmethod
 def machine_config_path(): return Path(os.environ.get("QUANTUM_STUDIO_LOCAL_TOOLS","~/.local/share/QuantumStudio/local_tools.json")).expanduser()

 @classmethod
 def load_machine_configuration(cls):
  path=cls.machine_config_path()
  try:
   data=json.loads(path.read_text(encoding="utf-8"))
   return cls(tool_paths=dict(data.get("tool_paths",{})),engine_directories=dict(data.get("engine_directories",{})),cpu_cores=int(data.get("cpu_cores",1)),omp_threads=int(data.get("omp_threads",1)),mpi_launcher=str(data.get("mpi_launcher","auto")),qe_bin_directory=str(data.get("qe_bin_directory","")),qe_version=str(data.get("qe_version","")))
  except (OSError,ValueError,json.JSONDecodeError,TypeError): return cls()
 def save_machine_configuration(self):
  path=self.machine_config_path(); path.parent.mkdir(parents=True,exist_ok=True); staging=path.with_suffix(path.suffix+".staging")
  data={"tool_paths":self.tool_paths,"engine_directories":self.engine_directories,"cpu_cores":self.cpu_cores,"omp_threads":self.omp_threads,"mpi_launcher":self.mpi_launcher,"qe_bin_directory":self.qe_bin_directory,"qe_version":self.qe_version}
  staging.write_text(json.dumps(data,sort_keys=True)+"\n",encoding="utf-8"); os.replace(staging,path)
 def apply_quantum_espresso(self, installation):
  self.qe_bin_directory=installation.bin_directory; self.qe_version=installation.version; self.engine_directories["quantum_espresso"]=installation.bin_directory; self.tool_paths.update(installation.tools)
 def resolve(self,tool_id,program,engine_id=None):
  candidates=[]
  if tool_id in self.tool_paths:
   configured=Path(self.tool_paths[tool_id]); candidates.append(configured / program if configured.is_dir() else configured)
  if engine_id and engine_id in self.engine_directories:candidates.append(Path(self.engine_directories[engine_id])/program)
  found=shutil.which(program,path=self.environment.get("PATH") or os.environ.get("PATH"))
  if found:candidates.append(Path(found))
  for candidate in candidates:
   if candidate.is_file() and os.access(candidate,os.X_OK): return candidate.resolve()
  if program == "bader":
   from .discovery import discover_bader
   found = discover_bader(environment=self.environment)
   if found: return Path(found[0]).resolve()
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
