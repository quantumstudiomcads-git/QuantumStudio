"""Conservative QE raw-artifact parsers. They never execute a scientific tool."""
from __future__ import annotations
import hashlib, re
from pathlib import Path
import numpy as np
from .models import ResultProvenance, ResultStatus, ScientificResult
from .volumetric import FIELD_SPECS, VolumetricParseError, parse_gaussian_cube
from .electronic import parse_bxsf, parse_bader_acf, parse_lowdin, parse_orbital_projection, parse_hubbard_parameters
from .optical import derive_optical_properties
RY_TO_EV=13.605693122994
class ResultParseError(RuntimeError): pass
def _prov(path, *, request_id="", execution_id="", task_id="", tool_id="", parser_id="qe", **_context):
 p=Path(path).resolve();
 if not p.is_file(): raise ResultParseError("Result source artifact is missing.")
 return ResultProvenance(request_id,execution_id,task_id,"quantum_espresso",tool_id,(str(p),),{str(p):hashlib.sha256(p.read_bytes()).hexdigest()},parser_id)
_QE_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"
_SCF_PATTERNS = {
    "total_energy": re.compile(r"!\s+total\s+energy\s*=\s*(" + _QE_NUMBER + r")\s+Ry\b", re.I),
    "fermi_energy": re.compile(r"the\s+Fermi\s+energy\s+is\s+(" + _QE_NUMBER + r")\s+e[vV]\b", re.I),
    "number_of_electrons": re.compile(r"number\s+of\s+electrons\s*=\s*(" + _QE_NUMBER + r")", re.I),
    "total_magnetization": re.compile(r"total\s+magnetization\s*=\s*(" + _QE_NUMBER + r")", re.I),
    "absolute_magnetization": re.compile(r"absolute\s+magnetization\s*=\s*(" + _QE_NUMBER + r")", re.I),
    "electronic_iterations": re.compile(r"iteration\s*#\s*(\d+)", re.I),
    "final_scf_accuracy": re.compile(r"estimated\s+scf\s+accuracy\s*<\s*(" + _QE_NUMBER + r")\s+Ry\b", re.I),
}

def _qe_float(value):
    return float(str(value).replace("D", "E").replace("d", "e"))

def parse_scf_output(path, **kwargs):
    """Parse the bounded v0.21 SCF scalar contract from QE pw.x stdout.

    Execution completion (C7 task state) and QE ``JOB DONE`` evidence are kept
    distinct from the electronic convergence marker.  Optional engine-reported
    values are omitted rather than assigned physically misleading defaults.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    provenance = _prov(path, tool_id="pw.x", parser_id="qe.pw.scf", **kwargs)
    values = {}
    iterations = None
    for line in text.splitlines():
        for key, pattern in _SCF_PATTERNS.items():
            match = pattern.search(line)
            if not match:
                continue
            if key == "electronic_iterations":
                iterations = int(match.group(1))
            else:
                values[key] = _qe_float(match.group(1))
    converged = bool(re.search(r"convergence\s+has\s+been\s+achieved", text, re.I))
    job_done = bool(re.search(r"\bJOB\s+DONE\.?", text, re.I))
    fatal_error = bool(re.search(r"\b(?:error in routine|%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%)\b", text, re.I))
    scalars = {}
    if "total_energy" in values:
        source = values["total_energy"]
        scalars["total_energy"] = {"value": source * RY_TO_EV, "unit": "eV", "source_value": source, "source_unit": "Ry"}
    if "fermi_energy" in values:
        scalars["fermi_energy"] = {"value": values["fermi_energy"], "unit": "eV"}
    if "number_of_electrons" in values:
        scalars["number_of_electrons"] = {"value": values["number_of_electrons"], "unit": "electrons"}
    for key in ("total_magnetization", "absolute_magnetization"):
        if key in values:
            scalars[key] = {"value": values[key], "unit": "Bohr magneton/cell", "source_unit": "Bohr mag/cell"}
    if iterations is not None:
        scalars["electronic_iterations"] = {"value": iterations, "unit": "iterations"}
    if "final_scf_accuracy" in values:
        source = values["final_scf_accuracy"]
        scalars["final_scf_accuracy"] = {"value": source * RY_TO_EV, "unit": "eV", "source_value": source, "source_unit": "Ry"}
    warnings = []
    if fatal_error:
        status = ResultStatus.PARSE_FAILED
        warnings.append("QE fatal-error marker was found in pw.x stdout.")
    elif not converged:
        status = ResultStatus.NOT_CONVERGED
        warnings.append("QE SCF convergence marker was not found.")
    elif "total_energy" not in scalars:
        status = ResultStatus.PARTIAL
        warnings.append("QE reported SCF convergence but no final total-energy line was found.")
    else:
        status = ResultStatus.VALID
    if not job_done:
        warnings.append("QE JOB DONE completion marker was not found; C7 execution state remains the authoritative process-completion record.")
    metadata = {"converged": converged, "job_done": job_done, "execution_completed_evidence": job_done, "fatal_error_marker": fatal_error, "contract_version": "v0.21-e1", "optional_scalars": ["fermi_energy", "total_magnetization", "absolute_magnetization"]}
    return ScientificResult("GroundStateResult", status, provenance, scalars, metadata=metadata, warnings=warnings)

def _numeric_rows(path):
    rows=[]
    for line in Path(path).read_text(encoding="utf-8",errors="replace").splitlines():
        if not line.strip() or line.lstrip().startswith(("#","!")): continue
        try: row=[_qe_float(value) for value in line.split()]
        except ValueError: continue
        if not row or not all(np.isfinite(row)): raise ResultParseError("Raw artifact contains a non-finite numeric value.")
        rows.append(row)
    if not rows: raise ResultParseError("Raw artifact contains no numeric data rows.")
    widths={len(row) for row in rows}
    if len(widths)!=1: raise ResultParseError("Raw artifact has inconsistent column counts.")
    return np.asarray(rows,float)

def _monotonic_energy(values):
    if len(values)<2 or not np.all(np.diff(values)>0): raise ResultParseError("Energy grid must be strictly increasing.")

def _source_headers(path):
    return [line.strip() for line in Path(path).read_text(encoding="utf-8",errors="replace").splitlines() if line.lstrip().startswith("#")]

def parse_dos(path, **kwargs):
    """Parse QE dos.x scalar/non-spin output without changing its raw energy axis."""
    data=_numeric_rows(path)
    method=(kwargs.get("method_metadata") or {}).get("spin_treatment", "SCALAR_NONSPIN")
    if method == "COLLINEAR_SPIN":
        headers="\n".join(_source_headers(path)).lower()
        if data.shape[1] != 4 or "dosup" not in headers or "dosdw" not in headers: raise ResultParseError("QE 7.6 collinear dos.x requires E, dosup(E), dosdw(E), Int dos(E).")
        energy=data[:,0]; _monotonic_energy(energy)
        fermi=re.search(r"EFermi\s*=\s*("+_QE_NUMBER+r")\s*eV",headers,re.I)
        scalars={}; metadata={"contract_version":"v0.21-e3","units":{"energy":"eV","dos_up":"states/eV/cell","dos_down":"states/eV/cell","integrated_dos":"states/cell"},"energy_reference":{"raw":"engine_output","display_default":"Fermi = 0" if fermi else "Absolute"},"normalization":"PER_CELL","source_energy_unit":"eV","spin_semantics":"COLLINEAR_SPIN","parser_diagnostics":[],"electronic_method":kwargs.get("method_metadata",{})}
        if fermi:
            value=_qe_float(fermi.group(1)); scalars["fermi_energy"]={"value":value,"unit":"eV"}; metadata["fermi_energy_eV"]=value; metadata["fermi_reference"]={"source":"dos.x header","source_task":"qe_dos","value_eV":value}
        integrated=data[:,3]
        if np.any(np.diff(integrated)<-1e-7): raise ResultParseError("Integrated DOS is not monotonic.")
        return ScientificResult("DOSResult",ResultStatus.VALID,_prov(path,tool_id="dos.x",parser_id="qe.dos",**kwargs),scalars=scalars,arrays={"energy":energy,"dos_up":data[:,1],"dos_down":data[:,2],"integrated_dos":integrated},metadata=metadata)
    if data.shape[1] not in (2,3): raise ResultParseError("QE non-spin dos.x output requires E, DOS(E), and optional integrated DOS columns.")
    energy=data[:,0]; _monotonic_energy(energy)
    headers="\n".join(_source_headers(path)); fermi=re.search(r"EFermi\s*=\s*("+_QE_NUMBER+r")\s*eV",headers,re.I)
    scalars={}
    metadata={"contract_version":"v0.21-e2","units":{"energy":"eV","dos":"states/eV/cell","integrated_dos":"states/cell"},"energy_reference":{"raw":"engine_output","display_default":"Fermi = 0" if fermi else "Absolute"},"normalization":"PER_CELL","source_energy_unit":"eV","spin_semantics":"SOC" if method == "SOC" else "NON_SPIN","parser_diagnostics":[]}
    if fermi:
        value=_qe_float(fermi.group(1)); scalars["fermi_energy"]={"value":value,"unit":"eV"}; metadata["fermi_energy_eV"]=value; metadata["fermi_reference"]={"source":"dos.x header","source_task":"qe_dos","value_eV":value}
    arrays={"energy":energy,"dos":data[:,1]}
    if data.shape[1]==3:
        integrated=data[:,2]
        if np.any(np.diff(integrated)<-1e-7): raise ResultParseError("Integrated DOS is not monotonic.")
        arrays["integrated_dos"]=integrated
    return ScientificResult("DOSResult",ResultStatus.VALID,_prov(path,tool_id="dos.x",parser_id="qe.dos",**kwargs),arrays=arrays,scalars=scalars,metadata=metadata)

def _columns(path, count, parser, result_type, names, **kwargs):
    data=_numeric_rows(path)
    if data.shape[1]<count: raise ResultParseError("Raw artifact has too few numeric columns.")
    arrays={name:data[:,index] for index,name in enumerate(names)}
    return ScientificResult(result_type,ResultStatus.VALID,_prov(path,tool_id=parser+".x",parser_id="qe."+parser,**kwargs),arrays=arrays,metadata={"units":{names[0]:"eV" if parser in {"bands","projwfc"} else "cm^-1"}})
def parse_phonon_dos(path, **kwargs): return _columns(path,2,"matdyn","PhononDOSResult",("frequency","dos"),**kwargs)
def parse_bands(path, **kwargs):
    """Parse QE bands.x filband output (header, k-point, energy blocks)."""
    lines=Path(path).read_text(encoding="utf-8",errors="replace").splitlines()
    header=next((line for line in lines if "nbnd=" in line and "nks=" in line), "")
    match=re.search(r"nbnd\s*=\s*(\d+).*nks\s*=\s*(\d+)", header, re.I)
    if not match: raise ResultParseError("QE bands artifact has no nbnd/nks header.")
    nbnd,nks=int(match.group(1)),int(match.group(2)); kpoints=[]; energies=[]; index=0
    while index < len(lines) and len(kpoints)<nks:
        try: values=[float(item) for item in lines[index].split()]
        except ValueError: index+=1; continue
        if len(values) < 3: index+=1; continue
        index += 1; band=[]
        while index < len(lines) and len(band)<nbnd:
            try: row=[float(item) for item in lines[index].split()]
            except ValueError: index+=1; continue
            band.extend(row); index += 1
        if len(band) < nbnd: break
        kpoints.append(values[:3]); energies.append(band[:nbnd])
    if len(kpoints) != nks: raise ResultParseError("QE bands artifact is truncated or malformed.")
    import numpy as np
    coords=np.asarray(kpoints,float); values=np.asarray(energies,float)
    path_coordinate=np.concatenate(([0.0],np.cumsum(np.linalg.norm(np.diff(coords,axis=0),axis=1))))
    metadata={"units":{"energies":"eV","kpoints":"crystal"},"kpoints":coords.tolist()}
    if kwargs.get("band_path") is not None:
        metadata["band_path"]=kwargs["band_path"]
        node_positions=[0]
        for point in kwargs["band_path"][:-1]: node_positions.append(node_positions[-1]+int(point.get("points",1)))
        metadata["path_node_positions"]=node_positions
        metadata["path_labels"]={position:point.get("label","") for position,point in zip(node_positions,kwargs["band_path"]) if point.get("label")}
    provenance={key:value for key,value in kwargs.items() if key in {"request_id","execution_id","task_id"}}
    return ScientificResult("BandStructureResult",ResultStatus.VALID,_prov(path,tool_id="bands.x",parser_id="qe.bands",**provenance),arrays={"path_coordinate":path_coordinate,"energies":values},metadata=metadata)

def parse_volumetric_cube(path, **kwargs):
    """Parse only a workflow-declared QE pp.x Gaussian cube artifact."""
    kind=str((kwargs.get("field_metadata") or {}).get("kind", "")).lower()
    if kind not in FIELD_SPECS: raise ResultParseError("Volumetric artifact has no supported declared field quantity.")
    try: values,cell,origin,shape=parse_gaussian_cube(path)
    except VolumetricParseError as error: raise ResultParseError(str(error)) from error
    spec=FIELD_SPECS[kind]; metadata={"contract_version":"v0.21-e4","quantity_kind":spec["quantity_kind"],"quantity_definition":spec["definition"],"source_format":"GAUSSIAN_CUBE","source_unit":spec["source_unit"],"unit":spec["unit"],"cell":cell.tolist(),"origin":origin.tolist(),"grid_shape":list(shape),"grid_coordinate_convention":"fractional i/n, j/n, k/n; periodic endpoint omitted","coordinate_convention":"row_vector r = origin + fractional @ cell","periodic":list((kwargs.get("field_metadata") or {}).get("periodic", [True,True,True])),"signed":spec["signed"],"pp_plot_num":spec["plot_num"],"electronic_method":kwargs.get("method_metadata",{}),"parser_diagnostics":[]}
    if kind=="elf" and (float(values.min()) < -1e-6 or float(values.max()) > 1.000001): metadata["parser_diagnostics"].append("ELF values fall outside the conventional [0, 1] range; raw values were preserved.")
    return ScientificResult("VolumetricResult",ResultStatus.VALID,_prov(path,tool_id="pp.x",parser_id="qe.pp.cube",**kwargs),arrays={"values":values},metadata=metadata)

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
for key,parser in (("QE_SCF_STDOUT",parse_scf_output),("BAND_STRUCTURE_RAW_DATA",parse_bands),("DOS_RAW_DATA",parse_dos),("PHONON_DOS_RAW_DATA",parse_phonon_dos),("VOLUMETRIC_RAW_DATA",parse_volumetric_cube)): DEFAULT_PARSERS.register(key,parser)

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
 status=ResultStatus.VALID if re.search(r"convergence has been achieved",text,re.I) else ResultStatus.NOT_CONVERGED
 forces=re.findall(r"Total force\s*=\s*("+_QE_NUMBER+r")",text,re.I)
 pressure=re.findall(r"P\s*=\s*("+_QE_NUMBER+r")",text,re.I)
 scalars={}
 if energies: scalars["total_energy"]={"value":float(energies[-1])*RY_TO_EV,"unit":"eV","source_value":float(energies[-1]),"source_unit":"Ry"}
 if forces: scalars["final_total_force"]={"value":_qe_float(forces[-1]),"unit":"Ry per bohr"}
 if pressure: scalars["final_pressure"]={"value":_qe_float(pressure[-1]),"unit":"kbar"}
 import numpy as _np
 metadata={"final_structure":structure.to_dict(),"vc_relax":bool(cells),"final_cell_A":cell,"final_volume_A3":abs(float(_np.linalg.det(cell))) if cell else None,"converged":status is ResultStatus.VALID,"job_done":bool(re.search(r"\bJOB\s+DONE\.?",text,re.I))}
 return ScientificResult("RelaxationResult",status,p,scalars,metadata=metadata)

def _prov_many(paths, **kwargs):
    first=Path(paths[0]).resolve(); provenance=_prov(first,**kwargs)
    resolved=tuple(str(Path(item).resolve()) for item in paths)
    return ResultProvenance(provenance.request_id,provenance.execution_id,provenance.source_task_id,provenance.engine_id,provenance.tool_id,resolved,{item:hashlib.sha256(Path(item).read_bytes()).hexdigest() for item in resolved},provenance.parser_id,provenance.parser_version,provenance.structure_fingerprint,provenance.workflow_fingerprint,provenance.public_intent)

def parse_pdos(path, **kwargs):
    """Parse bounded QE projwfc component files; values remain raw positive densities."""
    root=Path(path).resolve()
    if not root.is_dir(): raise ResultParseError("PDOS parser requires its generated projwfc directory.")
    files=sorted({item for pattern in ("*.pdos_atm#*","pdos_atm#*") for item in root.glob(pattern) if item.is_file()})
    if len(files)>4096: raise ResultParseError("PDOS component count exceeds the safe parser limit (4096).")
    if not files: raise ResultParseError("No QE PDOS component files were found in the generated task directory.")
    pattern=re.compile(r"(?:^|\.)pdos_atm#(\d+)\(([^)]+)\)_wfc#(\d+)\(([^)]+)\)")
    components=[]; energy=None; warnings=[]
    method=(kwargs.get("method_metadata") or {}).get("spin_treatment", "SCALAR_NONSPIN"); collinear=method == "COLLINEAR_SPIN"
    lmap={"s":0,"p":1,"d":2,"f":3}
    for item in files:
        match=pattern.search(item.name)
        if not match:
            warnings.append("Ignored malformed PDOS filename: "+item.name); continue
        try: data=_numeric_rows(item)
        except ResultParseError as error:
            warnings.append(item.name+": "+str(error)); continue
        if data.shape[1] < (5 if collinear else 3):
            warnings.append(item.name+(": QE 7.6 collinear PDOS requires E, ldosup, ldosdw, pdosup, pdosdw columns." if collinear else ": QE non-spin PDOS requires energy, integrated DOS, and total projected DOS columns.")); continue
        axis=data[:,0]
        try: _monotonic_energy(axis)
        except ResultParseError as error:
            warnings.append(item.name+": "+str(error)); continue
        if energy is not None and (len(axis)!=len(energy) or not np.allclose(axis,energy,rtol=1e-8,atol=1e-6)):
            raise ResultParseError("PDOS energy grids are incompatible; components are not interpolated.")
        energy=axis
        orbital=match.group(4).strip(); shell=orbital[:1].lower()
        if collinear:
            for spin,values,integrated in (("UP",data[:,3],data[:,1]),("DOWN",data[:,4],data[:,2])):
                component={"atom_index":int(match.group(1)),"atom":int(match.group(1)),"species":match.group(2).strip(),"orbital_index":int(match.group(3)),"orbital":shell if shell in lmap else orbital,"orbital_label":orbital,"l":lmap.get(shell),"spin":spin,"label":f"{match.group(2).strip()}({int(match.group(1))}) — {shell if shell in lmap else orbital} {"↑" if spin == "UP" else "↓"}","array_index":len(components),"source_filename":item.name,"raw_component_columns":max(0,int(data.shape[1]-5))}
                components.append((component,values,integrated))
            continue
        component={"atom_index":int(match.group(1)),"atom":int(match.group(1)),"species":match.group(2).strip(),"orbital_index":int(match.group(3)),"orbital":shell if shell in lmap else orbital,"orbital_label":orbital,"l":lmap.get(shell),"label":f"{match.group(2).strip()}({int(match.group(1))}) — {shell if shell in lmap else orbital}","array_index":len(components),"source_filename":item.name,"raw_component_columns":max(0,int(data.shape[1]-3))}
        components.append((component,data[:,2],data[:,1]))
    if not components: raise ResultParseError("No parseable QE PDOS components were found. "+" ".join(warnings))
    components.sort(key=lambda item:(item[0]["species"],item[0]["atom_index"],item[0]["l"] if item[0]["l"] is not None else 99,item[0]["orbital_index"],item[0]["source_filename"]))
    component_metadata=[]; component_values=[]; component_integrated=[]
    for index,(component,values,integrated) in enumerate(components):
        component["array_index"]=index; component_metadata.append(component); component_values.append(values.tolist())
        if integrated is not None: component_integrated.append(integrated.tolist())
    metadata={"contract_version":"v0.21-e2","components":component_metadata,"component_values":component_values,"units":{"energy":"eV","pdos":"states/eV/cell","integrated_pdos":"states/cell"},"energy_unit":"eV","normalization":"PER_CELL","source_energy_unit":"eV","spin_semantics":"COLLINEAR_SPIN" if collinear else "NON_SPIN","electronic_method":kwargs.get("method_metadata",{}),"parser_diagnostics":warnings,"energy_reference":{"raw":"engine_output","display_default":"Absolute"}}
    if component_integrated: metadata["component_integrated_values"]=component_integrated
    p=_prov_many(files,tool_id="projwfc.x",parser_id="qe.projwfc",**kwargs)
    status=ResultStatus.PARTIAL if warnings else ResultStatus.VALID
    return ScientificResult("PDOSResult",status,p,arrays={"energy":energy},metadata=metadata,warnings=warnings)

def parse_wannier_wout(path, **kwargs):
 text=Path(path).read_text(errors="replace"); p=_prov(path,tool_id="wannier90.x",parser_id="wannier90.wout",**kwargs)
 spread=re.findall(r"Final State.*?Spread\s+([-+0-9.Ee]+)",text,re.I); n=re.findall(r"Number of Wannier Functions\s*:\s*(\d+)",text,re.I)
 matches=list(re.finditer(r"WF\s+centre\s+and\s+spread\s+\d+\s+\(\s*("+_QE_NUMBER+r")\s*,\s*("+_QE_NUMBER+r")\s*,\s*("+_QE_NUMBER+r")\s*\)\s*("+_QE_NUMBER+r")",text,re.I))
 centres=np.asarray([[ _qe_float(match.group(i)) for i in (1,2,3)] for match in matches],float) if matches else np.empty((0,3))
 individual=np.asarray([_qe_float(match.group(4)) for match in matches],float) if matches else np.empty((0,))
 hr=Path(path).with_name(Path(path).stem+"_hr.dat")
 hr_metadata={}
 if hr.is_file():
  lines=hr.read_text(encoding="utf-8",errors="replace").splitlines()
  try: hr_metadata={"available":True,"num_wann":int(lines[1].strip()),"num_rpoints":int(lines[2].strip()),"source_path":str(hr.resolve()),"source_hash":hashlib.sha256(hr.read_bytes()).hexdigest()}
  except (IndexError,ValueError): hr_metadata={"available":True,"diagnostic":"Wannier HR header is malformed."}
 status=ResultStatus.VALID if re.search(r"All done|Wannierisation.*converged",text,re.I) else ResultStatus.PARTIAL
 scalars={"final_spread":{"value":float(spread[-1]),"unit":"angstrom^2"}} if spread else {}
 metadata={"num_wann":int(n[-1]) if n else None,"centres_unit":"angstrom","spread_unit":"angstrom^2","hr":hr_metadata,"converged":status is ResultStatus.VALID}
 arrays={}
 if len(centres): arrays["centres_A"]=centres; arrays["individual_spreads_A2"]=individual
 return ScientificResult("WannierizationResult",status,p,scalars,arrays=arrays,metadata=metadata)

def parse_epw_output(path, **kwargs):
 text=Path(path).read_text(errors="replace"); p=_prov(path,tool_id="epw.x",parser_id="epw.summary",**kwargs)
 runtime_complete = kwargs.get("execution_state") == "COMPLETED" and kwargs.get("return_code") == 0
 done=bool(re.search(r"JOB DONE|EPW.*completed",text,re.I)) or runtime_complete
 a2f_path=Path(kwargs.get("a2f_path", Path(path).with_suffix(".a2f")))
 if a2f_path.is_file():
  from backend.results.epw import parse_a2f, integrate_lambda, EPWParseError
  try:
   table=parse_a2f(a2f_path); alpha=table["alpha2f"][:,0]; lam=integrate_lambda(table["frequency_mev"],alpha)
   metadata={"completed_marker":done,"frequency_unit":"meV","alpha2f_unit":"EPW-native","series_count":int(table["alpha2f"].shape[1]),"lambda_integrated":lam}
   return ScientificResult("EliashbergFunctionResult",ResultStatus.VALID if done else ResultStatus.PARTIAL,p,scalars={"lambda_total":{"value":lam,"unit":"dimensionless"}},arrays={"frequency_mev":table["frequency_mev"],"alpha2f":table["alpha2f"]},metadata=metadata)
  except EPWParseError as error:
   return ScientificResult("EliashbergFunctionResult",ResultStatus.PARSE_FAILED,p,metadata={"completed_marker":done},warnings=[str(error)])
 return ScientificResult("ElectronPhononCouplingResult",ResultStatus.UNVERIFIED if done else ResultStatus.PARTIAL,p,metadata={"completed_marker":done},warnings=["EPW physical EPC observables are unavailable until a native EPW artifact is present."])

DEFAULT_PARSERS.register("PDOS_RAW_DATA",parse_pdos)
DEFAULT_PARSERS.register("QE_RELAX_STDOUT",parse_relax_output)
DEFAULT_PARSERS.register("WANNIER_WOUT",parse_wannier_wout)
DEFAULT_PARSERS.register("EPW_SUMMARY",parse_epw_output)
DEFAULT_PARSERS.register("FERMI_SURFACE_BXSF",parse_bxsf)
DEFAULT_PARSERS.register("BADER_ACF",parse_bader_acf)
DEFAULT_PARSERS.register("LOWDIN_POPULATION",parse_lowdin)
DEFAULT_PARSERS.register("ORBITAL_CHARACTER_RAW_DATA",parse_orbital_projection)
DEFAULT_PARSERS.register("HUBBARD_PARAMETER_RAW_DATA",parse_hubbard_parameters)


def _qe_matrix_numbers(text, count):
    values=[_qe_float(item) for item in re.findall(_QE_NUMBER, text)]
    if len(values) < count: raise ResultParseError("QE polar tensor block is incomplete.")
    return np.asarray(values[:count],dtype=float)

def parse_polar_gamma(path, **kwargs):
    source=Path(path); raw=source.read_text(encoding="utf-8",errors="replace")
    expected=int(kwargs.get("expected_atom_count") or 0)
    bec=[]
    epsilon=None
    if raw.lstrip().startswith("<"):
        import xml.etree.ElementTree as ET
        try: root=ET.fromstring(raw)
        except ET.ParseError as error: raise ResultParseError("QE polar XML is truncated or malformed.") from error
        eps_node=root.find(".//EPSILON")
        if eps_node is None: raise ResultParseError("QE polar XML is missing EPSILON.")
        epsilon=_qe_matrix_numbers(eps_node.text or "",9).reshape(3,3)
        nodes=root.findall(".//ZSTAR/*")
        for node in nodes:
            bec.append(_qe_matrix_numbers(node.text or "",9).reshape(3,3))
    else:
        eps_match=re.search(r"Dielectric Tensor:\s*(.*?)(?=Effective Charges|$)",raw,re.S|re.I)
        if not eps_match: raise ResultParseError("QE polar artifact is missing the dielectric tensor.")
        epsilon=_qe_matrix_numbers(eps_match.group(1),9).reshape(3,3)
        blocks=list(re.finditer(r"atom\s*#\s*(\d+)(.*?)(?=atom\s*#|$)",raw,re.S|re.I))
        for block in blocks: bec.append(_qe_matrix_numbers(block.group(2),9).reshape(3,3))
    if expected and len(bec)!=expected: raise ResultParseError(f"QE polar artifact returned {len(bec)} atoms; expected {expected}.")
    if not bec: raise ResultParseError("QE polar artifact is missing ZSTAR tensors.")
    bec=np.asarray(bec,dtype=float)
    if bec.shape != (len(bec),3,3) or epsilon.shape != (3,3): raise ResultParseError("QE polar tensor dimensions are invalid.")
    if not (np.all(np.isfinite(bec)) and np.all(np.isfinite(epsilon))): raise ResultParseError("QE polar tensors contain non-finite values.")
    residual=np.sum(bec,axis=0)
    metadata={"units":{"born_effective_charges":"e","epsilon_infinity":"dimensionless"},"epsilon_infinity":epsilon.tolist(),"bec_convention":"[atom, polarization Cartesian alpha, displacement Cartesian beta]","q_point_fractional":[0.,0.,0.],"backend":"Quantum ESPRESSO","backend_version":kwargs.get("backend_version","7.6"),"functional":kwargs.get("functional","PBE"),"spin_treatment":kwargs.get("spin_treatment","SCALAR_NONSPIN"),"polar_response":{"epsil":True,"zeu":True,"trans":True,"ldisp":False},"atom_elements":list(kwargs.get("atom_elements",[])),"pseudopotentials":kwargs.get("pseudopotentials",{}),"charge_sum_residual":residual.tolist(),"charge_sum_norm":float(np.linalg.norm(residual)),"symmetry_residual":(epsilon-epsilon.T).tolist(),"symmetry_residual_norm":float(np.linalg.norm(epsilon-epsilon.T)),"source_format":"QE_POLAR_FILDYN_XML" if raw.lstrip().startswith("<") else "QE_POLAR_FILDYN_TEXT"}
    return ScientificResult("BornEffectiveChargeResult",ResultStatus.VALID,_prov(source,tool_id="ph.x",parser_id="qe.ph.polar",**kwargs),arrays={"born_effective_charges":bec,"charge_sum_residual":residual},metadata=metadata)

def _parse_dynmat_rows(path, **kwargs):
    text=Path(path).read_text(encoding="utf-8",errors="replace")
    pattern=re.compile(r"freq\s*\(\s*(\d+)\s*\)\s*=\s*("+_QE_NUMBER+r")\s*\[THz\]\s*=\s*("+_QE_NUMBER+r")\s*\[cm-1\]",re.I)
    rows=[]
    for match in pattern.finditer(text): rows.append((int(match.group(1)),_qe_float(match.group(3)),_qe_float(match.group(2)),0.0))
    activity_text=kwargs.get("activity_text","")
    activity_rows=re.findall(r"^\s*(\d+)\s+("+_QE_NUMBER+r")\s+("+_QE_NUMBER+r")\s+("+_QE_NUMBER+r")\s*$",activity_text,re.M) if activity_text else []
    if not activity_rows or len(activity_rows)!=len(rows): raise ResultParseError("QE dynmat IR-activity rows do not match the eigenfrequency mode set.")
    rows=[(row[0],row[1],row[2],_qe_float(activity_rows[index][3])) for index,row in enumerate(rows)]
    if not rows: raise ResultParseError("QE dynmat output contains no mode/IR rows.")
    indices=np.asarray([row[0] for row in rows],dtype=int); cm1=np.asarray([row[1] for row in rows],dtype=float); thz=np.asarray([row[2] for row in rows],dtype=float); native=np.asarray([row[3] for row in rows],dtype=float)
    if not (np.all(np.isfinite(cm1)) and np.all(np.isfinite(thz)) and np.all(np.isfinite(native))): raise ResultParseError("QE dynmat mode data are non-finite.")
    return text,indices,cm1,thz,native

def parse_dynmat_frequencies(path):
    text=Path(path).read_text(encoding="utf-8",errors="replace")
    pattern=re.compile(r"freq\s*\(\s*(\d+)\s*\)\s*=\s*("+_QE_NUMBER+r")\s*\[THz\]\s*=\s*("+_QE_NUMBER+r")\s*\[cm-1\]",re.I)
    rows=pattern.findall(text)
    if not rows: raise ResultParseError("QE analytic dynmat output contains no mode frequencies.")
    indices=np.asarray([int(row[0]) for row in rows],dtype=int); thz=np.asarray([_qe_float(row[1]) for row in rows],dtype=float); cm1=np.asarray([_qe_float(row[2]) for row in rows],dtype=float)
    if not np.array_equal(indices,np.arange(1,len(indices)+1)) or not (np.all(np.isfinite(cm1)) and np.all(np.isfinite(thz))): raise ResultParseError("QE analytic dynmat mode data are invalid.")
    return {"frequencies_cm1":cm1,"frequencies_THz":thz}

def parse_dynmat_polar(path, **kwargs):
    text,indices,corrected_cm1,corrected_thz,native=_parse_dynmat_rows(path,**kwargs)
    expected=kwargs.get("expected_mode_count")
    if expected is not None and len(indices)!=int(expected): raise ResultParseError(f"QE dynmat returned {len(indices)} modes; expected {int(expected)}.")
    if not np.array_equal(indices,np.arange(1,len(indices)+1)): raise ResultParseError("QE dynmat mode indices are incomplete or out of order.")
    uncorrected_cm1=kwargs.get("uncorrected_frequencies_cm1"); uncorrected_thz=kwargs.get("uncorrected_frequencies_THz")
    if uncorrected_cm1 is None:
        uncorrected_cm1=corrected_cm1.copy(); uncorrected_thz=corrected_thz.copy(); reference="dynmat corrected values (analytic reference unavailable)"
    else:
        uncorrected_cm1=np.asarray(uncorrected_cm1,dtype=float); uncorrected_thz=np.asarray(uncorrected_thz,dtype=float)
        if uncorrected_cm1.shape!=corrected_cm1.shape or uncorrected_thz.shape!=corrected_thz.shape or not (np.all(np.isfinite(uncorrected_cm1)) and np.all(np.isfinite(uncorrected_thz))): raise ResultParseError("Uncorrected Gamma reference is incomplete.")
        reference=kwargs.get("uncorrected_reference","polar ph.x Gamma frequencies")
    direction=np.asarray(kwargs.get("direction",[1.,0.,0.]),dtype=float)
    if direction.shape!=(3,) or not np.all(np.isfinite(direction)) or np.linalg.norm(direction)<=1e-15: raise ResultParseError("QE dynmat direction is invalid.")
    direction=direction/np.linalg.norm(direction); result_type="IRResult" if kwargs.get("purpose")=="infrared" else "LOTOResult"
    arrays={"mode_indices":indices,"frequencies_cm1":corrected_cm1,"frequencies_THz":corrected_thz,"native_ir_quantity":native,"activity_mask":np.abs(native)>1e-12}
    metadata={"units":{"frequencies_cm1":"cm^-1","frequencies_THz":"THz","native_ir_quantity":"(D/A)^2/amu"},"native_ir_quantity":"IR activity","native_ir_unit":"(D/A)^2/amu","native_ir_definition":"QE dynmat discrete infrared activity; not a density per frequency interval","activity_mask":(np.abs(native)>1e-12).tolist(),"direction_unit_cartesian":direction.tolist(),"original_requested_direction":list(kwargs.get("original_direction",direction.tolist())),"asr":kwargs.get("asr","crystal"),"backend":"Quantum ESPRESSO","backend_version":kwargs.get("backend_version","7.6"),"uncorrected_reference":reference,"polar_artifact_provenance":kwargs.get("polar_artifact_provenance",{}),"mode_matching":"QE mode index; no sorting or invented degeneracy labels"}
    if result_type=="LOTOResult":
        arrays.update({"frequencies_uncorrected_cm1":uncorrected_cm1,"frequencies_uncorrected_THz":uncorrected_thz,"frequencies_nonanalytic_cm1":corrected_cm1,"frequencies_nonanalytic_THz":corrected_thz,"frequency_shifts_cm1":corrected_cm1-uncorrected_cm1,"frequency_shifts_THz":corrected_thz-uncorrected_thz}); metadata.update({"classification_method":"diagnostic only; QE mode index retained","classifications":["ambiguous"]*len(indices)})
    else: metadata.update({"quantity_name":"IR activity","activity_semantics":"discrete mode quantity"})
    return ScientificResult(result_type,ResultStatus.VALID,_prov(path,tool_id="dynmat.x",parser_id="qe.dynmat.polar",**kwargs),arrays=arrays,metadata=metadata)


def parse_phonon_dielectric(path, **kwargs):
    """Parse QE 7.6 dynmat lperm/lplasma analytic-Gamma output."""
    text=Path(path).read_text(encoding="utf-8", errors="replace")
    activity=str(kwargs.get("activity_text", "")); text=text+"\n"+activity; number=_QE_NUMBER
    scalar=r"(?:Infinity|"+number+r")"
    mode_rows=re.findall(r"^\s*(\d+)\s+("+number+r")\s+("+number+r")\s+("+number+r")\s+("+number+r")\s+("+number+r")\s+("+scalar+r")\s*$", activity, re.M)
    if not mode_rows: raise ResultParseError("QE dynmat lplasma output is missing mode dielectric rows.")
    indices=np.asarray([int(r[0]) for r in mode_rows],int); cm=np.asarray([_qe_float(r[1]) for r in mode_rows],float); z=np.asarray([[_qe_float(r[2]),_qe_float(r[3]),_qe_float(r[4])] for r in mode_rows],float); plasma=np.asarray([_qe_float(r[5]) for r in mode_rows],float); deps=np.asarray([_qe_float(r[6]) for r in mode_rows],float)
    freq_rows=re.findall(r"freq\s*\(\s*(\d+)\s*\)\s*=\s*("+number+r")\s*\[THz\]\s*=\s*("+number+r")\s*\[cm-1\]", text, re.I)
    if len(freq_rows)!=len(indices): raise ResultParseError("QE dielectric mode count does not match dynmat frequencies.")
    thz=np.asarray([_qe_float(r[1]) for r in freq_rows],float)
    eps_blocks=re.findall(r"(?:Electronic dielectric permittivity tensor \(relative, adimensional\)|with zone-center polar mode contributions)\s*\n((?:\s*"+number+r"\s+){2}"+number+r"\s*\n(?:\s*"+number+r"\s+){2}"+number+r"\s*\n(?:\s*"+number+r"\s+){2}"+number+r"\s*)", text, re.I)
    if len(eps_blocks)<2: raise ResultParseError("QE lperm output is missing electronic/static dielectric tensors.")
    mats=[np.asarray([_qe_float(x) for x in re.findall(number,b)],float).reshape(3,3) for b in eps_blocks[-2:]]; eps_inf,eps_static=mats; ionic=eps_static-eps_inf
    contributions=np.zeros((len(indices),3,3),float); included=np.zeros(len(indices),bool)
    for i,(vec,scalar) in enumerate(zip(z,deps)):
        norm=float(np.dot(vec,vec))
        if norm>1e-24 and abs(scalar)>1e-15: contributions[i]=scalar*np.outer(vec,vec)/norm; included[i]=True
    if not all(np.all(np.isfinite(x)) for x in (cm,thz,z,plasma,eps_inf,eps_static,contributions)) or not np.all(np.isfinite(deps[included])): raise ResultParseError("QE dielectric output contains non-finite values outside excluded acoustic rows.")
    residual=ionic-contributions.sum(axis=0)
    arrays={"epsilon_infinity":eps_inf,"epsilon_ionic":ionic,"epsilon_static":eps_static,"mode_indices":indices,"mode_frequencies_cm1":cm,"mode_frequencies_THz":thz,"mode_dielectric_contributions":contributions,"included_mode_mask":included,"mode_effective_charges":z,"mode_effective_plasma_frequencies_cm1":plasma}
    metadata={"units":{"epsilon_infinity":"dimensionless","epsilon_ionic":"dimensionless","epsilon_static":"dimensionless","mode_frequencies_cm1":"cm^-1","mode_frequencies_THz":"THz","mode_dielectric_contributions":"dimensionless"},"definition":"harmonic static dielectric tensor = electronic epsilon_infinity + analytic Gamma ionic mode sum","temperature_convention":"harmonic zero-temperature linear response","asr":kwargs.get("asr","crystal"),"source_format":"QE dynmat.x lperm/lplasma stdout","native_mode_quantity":"deps from QE polar_mode_permittivity; scalar trace with orientation from Z~* vector","native_mode_unit":"C^2/(J*m^2)","acoustic_policy":"retain rows, exclude non-hard modes as QE does (w2 <= eps8)","included_mode_mask":included.tolist(),"epsilon_ionic_sum_residual":residual.tolist(),"epsilon_ionic_sum_residual_norm":float(np.linalg.norm(residual)),"epsilon_static_relation_residual":(eps_static-eps_inf-ionic).tolist(),"symmetry_residual_norms":{"epsilon_infinity":float(np.linalg.norm(eps_inf-eps_inf.T)),"epsilon_ionic":float(np.linalg.norm(ionic-ionic.T)),"epsilon_static":float(np.linalg.norm(eps_static-eps_static.T))},"polar_artifact_provenance":kwargs.get("polar_artifact_provenance",{}),"backend":"Quantum ESPRESSO","backend_version":kwargs.get("backend_version","7.6"),"functional":kwargs.get("functional","PBE"),"spin_treatment":kwargs.get("spin_treatment","SCALAR_NONSPIN")}
    return ScientificResult("PhononDielectricResult",ResultStatus.VALID,_prov(path,tool_id="dynmat.x",parser_id="qe.dynmat.phonon_dielectric",**kwargs),arrays=arrays,metadata=metadata)

DEFAULT_PARSERS.register("QE_POLAR_GAMMA",parse_polar_gamma)
DEFAULT_PARSERS.register("QE_DYNMAT_POLAR",parse_dynmat_polar)
DEFAULT_PARSERS.register("QE_DYNMAT_PHONON_DIELECTRIC",parse_phonon_dielectric)


def parse_phonon_gamma(path, **kwargs):
    text=Path(path).read_text(encoding="utf-8",errors="replace")
    rows=re.findall(r"freq\s*\(\s*(\d+)\s*\)\s*=\s*("+_QE_NUMBER+r")\s*\[THz\]\s*=\s*("+_QE_NUMBER+r")\s*\[cm-1\]",text,re.I)
    expected=kwargs.get("expected_mode_count")
    if not rows or (expected is not None and len(rows)!=int(expected)): raise ResultParseError("QE phonon Gamma frequency block is incomplete.")
    thz=np.asarray([_qe_float(row[1]) for row in rows],float); cm1=np.asarray([_qe_float(row[2]) for row in rows],float)
    vectors=[]
    for block in re.findall(r"mode\s*#\s*\d+(.*?)(?=mode\s*#|$)",text,re.S|re.I):
        pairs=re.findall(r"\(\s*("+_QE_NUMBER+r")\s+("+_QE_NUMBER+r")\s*\)",block)
        if len(pairs)>=6: vectors.append([[_qe_float(pairs[3*a+b][0]) for b in range(3)] for a in range(2)])
    eigenvectors=np.asarray(vectors,float) if len(vectors)==len(rows) else np.empty((0,0,0))
    imaginary=cm1 < -1.0
    metadata={"q_point_fractional":[0.,0.,0.],"units":{"frequencies_THz":"THz","frequencies_cm1":"cm^-1"},"frequency_convention":"ordinary signed frequency; negative values are imaginary modes","imaginary_mode_count":int(np.count_nonzero(imaginary)),"imaginary_mode_mask":imaginary.tolist(),"acoustic_mode_indices":[0,1,2],"backend":"Quantum ESPRESSO","backend_version":kwargs.get("backend_version","7.6"),"fildyn":kwargs.get("fildyn"),"job_done":bool(re.search(r"\bJOB\s+DONE",text,re.I))}
    return ScientificResult("GammaPhononResult",ResultStatus.VALID,_prov(path,tool_id="ph.x",parser_id="qe.ph.gamma",**kwargs),arrays={"frequencies_THz":thz,"frequencies_cm1":cm1,"imaginary_mode_mask":imaginary,"eigenvectors":eigenvectors},metadata=metadata)


def parse_raman_output(path, **kwargs):
    """Parse native QE 7.6 Gamma Raman output from ph.x stdout."""
    text=Path(path).read_text(encoding="utf-8",errors="replace")
    freq_rows=re.findall(r"freq\s*\(\s*(\d+)\s*\)\s*=\s*("+_QE_NUMBER+r")\s*\[THz\]\s*=\s*("+_QE_NUMBER+r")\s*\[cm-1\]",text,re.I)
    if not freq_rows: raise ResultParseError("QE Raman output contains no Gamma mode frequencies.")
    indices=np.asarray([int(r[0]) for r in freq_rows],int); thz=np.asarray([_qe_float(r[1]) for r in freq_rows],float); cm=np.asarray([_qe_float(r[2]) for r in freq_rows],float)
    raw_tensor_text=str(kwargs.get("raman_tensor_text", kwargs.get("activity_text", "")))
    marker_match=re.search(r"Raman tensor \(A\^2\)",raw_tensor_text,re.I)
    displacement={}
    if marker_match:
        tail=raw_tensor_text[marker_match.end():]
        for match in re.finditer(r"atom\s*#\s*(\d+)\s+pol\.\s*(\d+)\s*\n((?:\s*"+_QE_NUMBER+r"\s+"+_QE_NUMBER+r"\s+"+_QE_NUMBER+r"\s*\n){3})",tail,re.I):
            rows=[[ _qe_float(x) for x in line.split()] for line in match.group(3).splitlines() if line.strip()]
            if len(rows)==3: displacement[(int(match.group(1))-1,int(match.group(2))-1)]=rows
    tensors=[]
    # dynmat prints two real/imag rows per mode; project the atomic
    # displacement response tensor onto the mass-normalized eigenvector.
    for block in re.split(r"(?=freq\s*\(\s*\d+\s*\))",text,flags=re.I)[1:]:
        pairs=re.findall(r"\(\s*((?:"+_QE_NUMBER+r"\s+){5}"+_QE_NUMBER+r")\s*\)",block)
        if len(pairs)<2 or not displacement: continue
        vec=[]
        for pair in pairs[:len(displacement)//3]:
            vals=[_qe_float(x) for x in pair.split()]
            vec.append([vals[0],vals[2],vals[4]])
        if len(vec)*3 != len(displacement): continue
        tensor=np.zeros((3,3),float)
        for (atom,pol),matrix in displacement.items(): tensor += np.asarray(matrix)*vec[atom][pol]
        tensors.append(tensor)
    if len(tensors)!=len(indices): raise ResultParseError("QE Raman tensor/eigenvector data do not match the mode count.")
    tensor_array=np.asarray(tensors,float)
    activity_rows=re.findall(r"^\s*(\d+)\s+("+_QE_NUMBER+r")\s+("+_QE_NUMBER+r")\s+("+_QE_NUMBER+r")\s+("+_QE_NUMBER+r")\s+("+_QE_NUMBER+r")\s*$",(text+"\n"+str(kwargs.get("activity_text", ""))),re.M)
    activities=[]; depol=[]
    for row in activity_rows:
        if int(row[0])<=len(indices): activities.append(_qe_float(row[4])); depol.append(_qe_float(row[5]))
    if len(activities)!=len(indices): raise ResultParseError("QE Raman activity table is missing or does not match the mode count.")
    activities=np.asarray(activities,float); depol=np.asarray(depol,float)
    if not all(np.all(np.isfinite(x)) for x in (cm,thz,tensor_array,activities,depol)): raise ResultParseError("QE Raman data contain non-finite values.")
    active=np.any(np.abs(tensor_array)>1.e-12,axis=(1,2))
    completion_text=text+"\n"+str(kwargs.get("activity_text", ""))
    metadata={"units":{"frequencies_cm1":"cm^-1","frequencies_THz":"THz","raman_tensors":"A^2/amu^1/2","raman_activity":"A^4/amu","depolarization_ratio":"dimensionless"},"tensor_quantity_name":"Raman tensor dX/dQ","tensor_definition":"QE non-resonant derivative of dielectric/polarizability response with respect to mass-normalized normal coordinate","tensor_orientation":"[mode, Cartesian alpha, Cartesian beta]","activity_definition":"QE Raman invariant activity from isotropic and anisotropic tensor invariants","activity_unit":"A^4/amu","raman_active_mask":active.tolist(),"backend":"Quantum ESPRESSO","backend_version":kwargs.get("backend_version","7.6"),"functional":kwargs.get("functional","PZ"),"pseudo_provenance":kwargs.get("pseudopotentials",{}),"calculation_settings":kwargs.get("calculation_settings",{}),"asr":kwargs.get("asr","crystal"),"job_done":bool(re.search(r"\bJOB\s+DONE",completion_text,re.I))}
    provenance_kwargs=dict(kwargs); tool_id=provenance_kwargs.pop("tool_id","ph.x")
    return ScientificResult("RamanResult",ResultStatus.VALID,_prov(path,tool_id=tool_id,parser_id="qe.ph.raman",**provenance_kwargs),arrays={"mode_indices":indices,"frequencies_cm1":cm,"frequencies_THz":thz,"raman_tensors":tensor_array,"raman_activity":activities,"depolarization_ratio":depol,"raman_active_mask":active},metadata=metadata)

def parse_phonon_dispersion(path, **kwargs):
    lines=Path(path).read_text(encoding="utf-8",errors="replace").splitlines(); q=[]; values=[]; index=0; branch_count=int(kwargs.get("branch_count") or 0)
    while index < len(lines):
        try: qrow=[_qe_float(item) for item in lines[index].split()]
        except ValueError: index+=1; continue
        if len(qrow)<3: index+=1; continue
        try: frow=[_qe_float(item) for item in lines[index+1].split()]
        except (ValueError,IndexError): index+=1; continue
        if branch_count and len(frow)<branch_count: index+=1; continue
        q.append(qrow[:3]); values.append(frow[:branch_count] if branch_count else frow); index+=2
    if not q: raise ResultParseError("Phonon dispersion output contains no q-point rows.")
    qarr=np.asarray(q,float); frequencies=np.asarray(values,float)
    if frequencies.ndim!=2 or not np.all(np.isfinite(frequencies)): raise ResultParseError("Phonon dispersion contains invalid frequencies.")
    cell=np.asarray(kwargs.get("cell_A",np.eye(3)),float); reciprocal=2*np.pi*np.linalg.inv(cell).T; cart=qarr@reciprocal; distance=np.concatenate(([0.],np.cumsum(np.linalg.norm(np.diff(cart,axis=0),axis=1))))
    return ScientificResult("PhononDispersionResult",ResultStatus.VALID,_prov(path,tool_id="matdyn.x",parser_id="qe.matdyn.dispersion",**kwargs),arrays={"q_points_fractional":qarr,"q_distance":distance,"frequencies_cm1":frequencies,"frequencies_THz":frequencies/33.3564095},metadata={"units":{"frequencies_cm1":"cm^-1","frequencies_THz":"THz","q_points":"fractional reciprocal coordinates","q_distance":"Å^-1"},"asr":kwargs.get("asr","crystal"),"q_coordinate":"crystal_fractional","backend":"Quantum ESPRESSO","backend_version":kwargs.get("backend_version","7.6"),"high_symmetry_labels":kwargs.get("high_symmetry_labels",[]),"high_symmetry_indices":kwargs.get("high_symmetry_indices",[])})

def parse_btp2_transport(path, **kwargs):
    from .transport import parse_transport_result
    return parse_transport_result(path,**kwargs)

DEFAULT_PARSERS.register("QE_PHONON_GAMMA",parse_phonon_gamma)
DEFAULT_PARSERS.register("QE_RAMAN",parse_raman_output)
DEFAULT_PARSERS.register("PHONON_DISPERSION_RAW_DATA",parse_phonon_dispersion)
DEFAULT_PARSERS.register("BTP2_TRANSPORT_JSON",parse_btp2_transport)



def parse_qe_epsilon(path, **kwargs):
    """Parse QE 7.6 eps mode's structured diagonal Cartesian spectra."""
    directory = Path(path).resolve()
    if not directory.is_dir():
        raise ResultParseError("QE epsilon.x source must be its task working directory.")
    prefix = str(kwargs.get("qe_prefix", "")).strip()
    if not prefix:
        candidates = sorted(directory.glob("epsr_*.dat"))
        if len(candidates) != 1:
            raise ResultParseError("QE epsilon.x real dielectric spectrum is ambiguous or missing.")
        real_source = candidates[0]
        prefix = real_source.name[len("epsr_"):-len(".dat")]
    else:
        real_source = directory / f"epsr_{prefix}.dat"
    imaginary_source = directory / f"epsi_{prefix}.dat"
    if not real_source.is_file() or not imaginary_source.is_file() or not real_source.stat().st_size or not imaginary_source.stat().st_size:
        raise ResultParseError("QE epsilon.x epsr/epsi spectral artifacts are missing or empty.")
    real, imaginary = _numeric_rows(real_source), _numeric_rows(imaginary_source)
    if real.shape[1] != 4 or imaginary.shape[1] != 4:
        raise ResultParseError("QE epsilon.x eps mode requires energy plus xx/yy/zz columns in epsr and epsi files.")
    energy = real[:, 0]
    _monotonic_energy(energy)
    if imaginary.shape != real.shape or not np.allclose(imaginary[:, 0], energy, rtol=0.0, atol=1.0e-8):
        raise ResultParseError("QE epsilon.x epsr and epsi files do not share one energy grid.")
    arrays = {"energy_eV": energy}
    for index, component in enumerate(("xx", "yy", "zz"), start=1):
        arrays[f"epsilon1_{component}"] = real[:, index]
        arrays[f"epsilon2_{component}"] = imaginary[:, index]
    diagonal = np.vstack([arrays[f"epsilon1_{component}"] for component in ("xx", "yy", "zz")])
    imaginary_diagonal = np.vstack([arrays[f"epsilon2_{component}"] for component in ("xx", "yy", "zz")])
    sources = (real_source, imaginary_source)
    hashes = {str(source): hashlib.sha256(source.read_bytes()).hexdigest() for source in sources}
    provenance = ResultProvenance(str(kwargs.get("request_id", "")), str(kwargs.get("execution_id", "")), str(kwargs.get("task_id", "")), "quantum_espresso", "epsilon.x", tuple(str(source) for source in sources), hashes, "qe.epsilon.eps", "1")
    metadata = {
        "source_format": "QE 7.6 epsilon.x epsr_<prefix>.dat / epsi_<prefix>.dat",
        "epsilon_convention": "epsilon(E) = epsilon1(E) + i epsilon2(E)",
        "tensor_convention": "Diagonal Cartesian epsilon_xx, epsilon_yy, epsilon_zz from QE epsilon.x eps mode; off-diagonal components are not emitted by this selected mode.",
        "polarization_convention": "Cartesian laboratory axes of the QE input cell.",
        "units": {"energy_eV": "eV", **{f"epsilon{part}_{component}": "dimensionless" for component in ("xx", "yy", "zz") for part in ("1", "2")}},
        "response_scope": ((kwargs.get("optical_settings") or {}).get("scope") or "Independent-particle RPA dielectric response (QE epsilon.x dipole approximation); no excitons, BSE, GW, or local-field corrections."),
        "optical_settings": kwargs.get("optical_settings", {}),
        "electronic_method": kwargs.get("method_metadata", {}),
        "symmetry_residual": {"epsilon1_diagonal_max_span": float(np.max(np.ptp(diagonal, axis=0))), "epsilon2_diagonal_max_span": float(np.max(np.ptp(imaginary_diagonal, axis=0)))},
    }
    return ScientificResult("OpticalDielectricResult", ResultStatus.VALID, provenance, arrays=arrays, metadata=metadata)


DEFAULT_PARSERS.register("QE_EPSILON_TENSOR", parse_qe_epsilon)
