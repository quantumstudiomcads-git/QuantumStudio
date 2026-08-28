"""Conservative QE raw-artifact parsers. They never execute a scientific tool."""
from __future__ import annotations
import hashlib, re
from pathlib import Path
import numpy as np
from .models import ResultProvenance, ResultStatus, ScientificResult
from .volumetric import FIELD_SPECS, VolumetricParseError, parse_gaussian_cube
from .electronic import parse_bxsf, parse_bader_acf, parse_lowdin, parse_orbital_projection, parse_hubbard_parameters
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
 done=bool(re.search(r"JOB DONE|EPW.*completed",text,re.I))
 return ScientificResult("ElectronPhononResult",ResultStatus.UNVERIFIED if done else ResultStatus.PARTIAL,p,metadata={"completed_marker":done},warnings=["No EPW physical observable is parsed in C8C."])

DEFAULT_PARSERS.register("PDOS_RAW_DATA",parse_pdos)
DEFAULT_PARSERS.register("QE_RELAX_STDOUT",parse_relax_output)
DEFAULT_PARSERS.register("WANNIER_WOUT",parse_wannier_wout)
DEFAULT_PARSERS.register("EPW_SUMMARY",parse_epw_output)
DEFAULT_PARSERS.register("FERMI_SURFACE_BXSF",parse_bxsf)
DEFAULT_PARSERS.register("BADER_ACF",parse_bader_acf)
DEFAULT_PARSERS.register("LOWDIN_POPULATION",parse_lowdin)
DEFAULT_PARSERS.register("ORBITAL_CHARACTER_RAW_DATA",parse_orbital_projection)
DEFAULT_PARSERS.register("HUBBARD_PARAMETER_RAW_DATA",parse_hubbard_parameters)
