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

def parse_relax_output(path, **kwargs):
 text=Path(path).read_text(encoding="utf-8",errors="replace"); p=_prov(path,tool_id="pw.x",parser_id="qe.pw.relax",**kwargs)
 energies=re.findall(r"!\s+total energy\s+=\s+([-+0-9.Ee]+)\s+Ry",text)
 blocks=re.findall(r"ATOMIC_POSITIONS\s+(angstrom|bohr)\s*\n((?:[^\n]+\n)+?)(?=\n\S|\Z)",text,re.I)
 if not blocks: raise ResultParseError("No final QE ATOMIC_POSITIONS block.")
 unit,body=blocks[-1]; atoms=[]
 from frontend.core.structure import Atom, Structure
 scale=0.529177210903 if unit.lower()=="bohr" else 1.0
 for line in body.strip().splitlines():
  part=line.split()
  if len(part)<4: continue
  atoms.append(Atom(part[0],float(part[1])*scale,float(part[2])*scale,float(part[3])*scale))
 if not atoms: raise ResultParseError("Final QE geometry block is malformed.")
 cells=re.findall(r"CELL_PARAMETERS\s+(angstrom|bohr)\s*\n([^\n]+\n[^\n]+\n[^\n]+)",text,re.I); cell=None
 if cells:
  cu,body=cells[-1]; factor=.529177210903 if cu.lower()=="bohr" else 1.; cell=[[float(x)*factor for x in line.split()[:3]] for line in body.splitlines()]
 structure=Structure(atoms=atoms,cell=cell or [[10.,0,0],[0,10.,0],[0,0,10.]],name="Relaxed Structure")
 status=ResultStatus.VALID if re.search(r"convergence has been achieved|JOB DONE",text,re.I) else ResultStatus.NOT_CONVERGED
 scalars={}
 if energies: scalars["total_energy"]={"value":float(energies[-1])*RY_TO_EV,"unit":"eV","source_value":float(energies[-1]),"source_unit":"Ry"}
 return ScientificResult("RelaxationResult",status,p,scalars,metadata={"final_structure":structure.to_dict(),"vc_relax":bool(cells)})

def parse_pdos(path, **kwargs):
 root=Path(path).resolve(); files=[root] if root.is_file() else sorted(root.glob("pdos_atm#*"))
 if not files or any(root not in item.resolve().parents and item.resolve()!=root for item in files): raise ResultParseError("No safe PDOS sources found.")
 components=[]; energy=None
 for item in files:
  match=re.search(r"atm#(\d+)\(([^)]+)\)_wfc#(\d+)\(([^)]+)\)",item.name)
  if not match: continue
  data=[]
  for line in item.read_text(errors="replace").splitlines():
   try: data.append([float(x) for x in line.split()])
   except ValueError: pass
  if not data: continue
  array=np.asarray(data); axis=array[:,0]
  if energy is not None and (len(axis)!=len(energy) or not np.allclose(axis,energy)): raise ResultParseError("PDOS energy grids are incompatible.")
  energy=axis; components.append({"atom_index":int(match.group(1)),"species":match.group(2),"orbital_index":int(match.group(3)),"orbital_label":match.group(4),"values":array[:,1:]})
 if energy is None: raise ResultParseError("PDOS files contain no data.")
 p=_prov(files[0],tool_id="projwfc.x",parser_id="qe.projwfc",**kwargs)
 return ScientificResult("PDOSResult",ResultStatus.VALID,p,arrays={"energy":energy},metadata={"components":[{**{k:v for k,v in c.items() if k!="values"},"array_index":i} for i,c in enumerate(components)] ,"component_values":[c["values"].tolist() for c in components],"energy_unit":"eV"})

def parse_wannier_wout(path, **kwargs):
 text=Path(path).read_text(errors="replace"); p=_prov(path,tool_id="wannier90.x",parser_id="wannier90.wout",**kwargs)
 spread=re.findall(r"Final State.*?Spread\s+([-+0-9.Ee]+)",text,re.I); n=re.findall(r"Number of Wannier Functions\s*:\s*(\d+)",text,re.I)
 status=ResultStatus.VALID if re.search(r"All done|Wannierisation.*converged",text,re.I) else ResultStatus.PARTIAL
 scalars={"final_spread":{"value":float(spread[-1]),"unit":"angstrom^2"}} if spread else {}
 return ScientificResult("WannierizationResult",status,p,scalars,metadata={"num_wann":int(n[-1]) if n else None})

def parse_epw_output(path, **kwargs):
 text=Path(path).read_text(errors="replace"); p=_prov(path,tool_id="epw.x",parser_id="epw.summary",**kwargs)
 done=bool(re.search(r"JOB DONE|EPW.*completed",text,re.I))
 return ScientificResult("ElectronPhononResult",ResultStatus.UNVERIFIED if done else ResultStatus.PARTIAL,p,metadata={"completed_marker":done},warnings=["No EPW physical observable is parsed in C8C."])

DEFAULT_PARSERS.register("PDOS_RAW_DATA",parse_pdos)
DEFAULT_PARSERS.register("QE_RELAX_STDOUT",parse_relax_output)
DEFAULT_PARSERS.register("WANNIER_WOUT",parse_wannier_wout)
DEFAULT_PARSERS.register("EPW_SUMMARY",parse_epw_output)
