"""Conservative QE raw-artifact parsers. They never execute a scientific tool."""
from __future__ import annotations
import hashlib, re
from pathlib import Path
import numpy as np
from .models import ResultProvenance, ResultStatus, ScientificResult
RY_TO_EV=13.605693122994
class ResultParseError(RuntimeError): pass
def _prov(path, *, request_id="", execution_id="", task_id="", tool_id="", parser_id="qe"):
 p=Path(path).resolve();
 if not p.is_file(): raise ResultParseError("Result source artifact is missing.")
 return ResultProvenance(request_id,execution_id,task_id,"quantum_espresso",tool_id,(str(p),),{str(p):hashlib.sha256(p.read_bytes()).hexdigest()},parser_id)
def parse_scf_output(path, **kwargs):
 text=Path(path).read_text(encoding="utf-8",errors="replace"); p=_prov(path,tool_id="pw.x",parser_id="qe.pw.scf",**kwargs); scalars={}; warnings=[]
 energy=re.findall(r"!\s+total energy\s+=\s+([-+0-9.Ee]+)\s+Ry",text)
 if energy: scalars["total_energy"]={"value":float(energy[-1])*RY_TO_EV,"unit":"eV","source_value":float(energy[-1]),"source_unit":"Ry"}
 fermi=re.findall(r"the Fermi energy is\s+([-+0-9.Ee]+)\s+ev",text,re.I)
 if fermi: scalars["fermi_energy"]={"value":float(fermi[-1]),"unit":"eV"}
 for name,pattern in (("total_magnetization",r"total magnetization\s+=\s+([-+0-9.Ee]+)"),("absolute_magnetization",r"absolute magnetization\s+=\s+([-+0-9.Ee]+)")):
  found=re.findall(pattern,text,re.I)
  if found: scalars[name]={"value":float(found[-1]),"unit":"Bohr magneton"}
 converged=bool(re.search(r"convergence has been achieved",text,re.I)); status=ResultStatus.VALID if converged else ResultStatus.NOT_CONVERGED
 if not converged:warnings.append("QE SCF convergence marker was not found.")
 return ScientificResult("GroundStateResult",status,p,scalars,metadata={"converged":converged},warnings=warnings)
def _columns(path, count, parser, result_type, names, **kwargs):
 rows=[]
 for line in Path(path).read_text(encoding="utf-8",errors="replace").splitlines():
  if not line.strip() or line.lstrip().startswith(("#","!")): continue
  try: values=[float(x) for x in line.split()]
  except ValueError: continue
  if len(values)>=count: rows.append(values[:count])
 if not rows: raise ResultParseError("Raw artifact contains no numeric data rows.")
 data=np.asarray(rows,float); arrays={name:data[:,index] for index,name in enumerate(names)}; return ScientificResult(result_type,ResultStatus.VALID,_prov(path,tool_id=parser+".x",parser_id="qe."+parser,**kwargs),arrays=arrays,metadata={"units":{names[0]:"eV" if parser in {"dos","bands","projwfc"} else "cm^-1"}})
def parse_dos(path, **kwargs): return _columns(path,2,"dos","DOSResult",("energy","dos"),**kwargs)
def parse_phonon_dos(path, **kwargs): return _columns(path,2,"matdyn","PhononDOSResult",("frequency","dos"),**kwargs)
def parse_bands(path, **kwargs): return _columns(path,2,"bands","BandStructureResult",("path_coordinate","energy"),**kwargs)
class ParserRegistry:
 def __init__(self): self._parsers={}
 def register(self,key,parser):
  if key in self._parsers: raise ResultParseError("Duplicate parser registration: "+key)
  self._parsers[key]=parser
 def parse(self,key,path,**kwargs):
  if key not in self._parsers: raise ResultParseError("No parser for artifact: "+key)
  return self._parsers[key](path,**kwargs)
 def validate(self): return tuple(sorted(self._parsers))
DEFAULT_PARSERS=ParserRegistry()
for key,parser in (("QE_SCF_STDOUT",parse_scf_output),("BAND_STRUCTURE_RAW_DATA",parse_bands),("DOS_RAW_DATA",parse_dos),("PHONON_DOS_RAW_DATA",parse_phonon_dos)): DEFAULT_PARSERS.register(key,parser)
