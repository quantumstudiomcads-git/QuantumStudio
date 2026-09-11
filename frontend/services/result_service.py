"""Qt-free Calculate-facing access to C8 execution-sidecar Results."""
from __future__ import annotations
import json
import re
import numpy as np
from pathlib import Path
from backend.execution import ExecutionStore
from backend.execution.models import TaskState
from backend.results import DEFAULT_PARSERS, ResultStore, ResultStoreError, ResultParseError, ResultStatus
from backend.results.parsers import parse_dynmat_frequencies
from backend.results.models import ScientificResult
from backend.results.derived import derive_band_gap, derive_effective_mass, derive_charge_transfer, derive_magnetic_moments


def _qe_input_setting(text, key):
 match=re.search(r"^\s*"+re.escape(key)+r"\s*=\s*([^,!\n]+)",text,re.M|re.I)
 if not match: return None
 value=match.group(1).strip().strip("'\"")
 try: return float(value.replace("D","E").replace("d","e"))
 except ValueError: return value

def _raman_calculation_settings(root, manifest, lineage, dynmat_task):
 settings={}
 for parent_id in lineage:
  parent=manifest.get(parent_id,{})
  directory=(Path(root)/str(parent.get("working_directory",""))).resolve()
  semantic=str(parent.get("semantic_task_type") or (parent.get("metadata") or {}).get("semantic_task_type", ""))
  input_name=str(parent.get("input_filename", ""))
  input_path=directory/input_name
  if not input_path.is_file(): continue
  text=input_path.read_text(encoding="utf-8",errors="replace")
  if semantic == "scf":
   for key in ("ecutwfc","ecutrho","conv_thr"):
    value=_qe_input_setting(text,key)
    if value is not None: settings[key]=value
   mesh=re.search(r"K_POINTS\s+automatic\s*\n\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",text,re.I)
   if mesh: settings["kpoints"]={"mode":"automatic","mesh":[int(mesh.group(i)) for i in range(1,4)],"shifts":[int(mesh.group(i)) for i in range(4,7)]}
  if semantic in {"raman","qe_raman"}:
   for key in ("eth_rps","eth_ns","dek","tr2_ph"):
    value=_qe_input_setting(text,key)
    if value is not None: settings[key]=value
 dynmat_directory=(Path(root)/str(dynmat_task.get("working_directory",""))).resolve()
 dynmat_input=dynmat_directory/str(dynmat_task.get("input_filename",""))
 if dynmat_input.is_file():
  value=_qe_input_setting(dynmat_input.read_text(encoding="utf-8",errors="replace"),"asr")
  if value is not None: settings["asr"]=value
 return settings


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
  names={"qe_polar_gamma":("polar_gamma.xml","polar_gamma"), "qe_bands":("bands.dat",), "qe_fs":("fermi_surface.bxsf","*_fs.bxsf","*.bxsf"), "qe_dos":("dos.dat",), "qe_matdyn":("phonon_dos.dat","matdyn.dos","phdos.dat","phonon.dos","phonon_dispersion.freq","matdyn.freq"), "raman":("dynmat.out","raman.dynmat.out"), "qe_raman":("raman.out",), "qe_dynmat":("lo_to.dynmat.out","lo_to_1.dynmat.out","lo_to_2.dynmat.out","lo_to_3.dynmat.out","infrared.dynmat.out","*.dynmat.out","dynmat.out"), "phonons":(), "qe_projwfc":("*.pdos_atm#*","pdos_atm#*","*.projwfc_up"), "qe_pp":(), "qe_bader":("ACF.dat",), "qe_hp":("*.Hubbard_parameters.dat",), "qe_epsilon":(), "btp2_transport":("transport.json",)}
  if semantic=="qe_epsilon": return directory
  if semantic=="wannier90_run":
   candidates=sorted(directory.glob("*.wout"))
   if len(candidates)==1 and directory in candidates[0].resolve().parents: return candidates[0]
   if len(candidates)>1: raise ResultStoreError("Wannier result discovery found multiple .wout files in the task directory.")
  if semantic=="qe_pp":
   field=((task.get("metadata") or {}).get("task_metadata") or {}).get("field",{})
   candidate=(directory/str(field.get("artifact",""))).resolve()
   if candidate.is_file() and directory in candidate.parents: return candidate
  for name in names.get(semantic,()):
   if "*" in name:
    candidates=sorted(directory.glob(name))
    if candidates and all(directory in candidate.resolve().parents for candidate in candidates):
     return directory if semantic == "qe_projwfc" else candidates[0]
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
  analytic_references={}
  for reference_id, reference_task in manifest.items():
   reference_meta=(reference_task.get("metadata",{}) or {}).get("task_metadata",{}) or {}
   if reference_meta.get("purpose") != "analytic_reference": continue
   runtime=record.tasks.get(reference_id)
   source=self._source(root,reference_task,runtime,"qe_dynmat") if runtime is not None and runtime.state is TaskState.COMPLETED else None
   if source is not None: analytic_references[reference_meta.get("parent_polar_task_id")]=parse_dynmat_frequencies(source)
  for parent_id, parent_task in manifest.items():
   if (parent_task.get("metadata",{}) or {}).get("semantic_task_type") != "qe_polar_gamma": continue
   candidate=(root/str(parent_task.get("working_directory", ""))/"analytic_reference.dynmat.out").resolve()
   if candidate.is_file(): analytic_references[parent_id]=parse_dynmat_frequencies(candidate)
  parsed=[]; errors=[]
  parsed_by_task={}
  def ancestors(task_id):
   seen=set(); stack=list(manifest.get(task_id,{}).get("dependencies",()) or ())
   while stack:
    parent=str(stack.pop())
    if parent in seen: continue
    seen.add(parent); stack.extend(manifest.get(parent,{}).get("dependencies",()) or ())
   return tuple(sorted(seen))
  routes={"scf":"QE_SCF_STDOUT","relax":"QE_RELAX_STDOUT","vc_relax":"QE_RELAX_STDOUT","qe_bands":"BAND_STRUCTURE_RAW_DATA","qe_fs":"FERMI_SURFACE_BXSF","qe_bader":"BADER_ACF","qe_lowdin":"LOWDIN_POPULATION","qe_hp":"HUBBARD_PARAMETER_RAW_DATA","qe_dos":"DOS_RAW_DATA","qe_matdyn":"PHONON_DOS_RAW_DATA","qe_matdyn_dos":"PHONON_DOS_RAW_DATA","qe_matdyn_dispersion":"PHONON_DISPERSION_RAW_DATA","qe_projwfc":"PDOS_RAW_DATA","qe_pp":"VOLUMETRIC_RAW_DATA","wannier90_run":"WANNIER_WOUT","epw":"EPW_SUMMARY","epw_run":"EPW_SUMMARY","btp2_transport":"BTP2_TRANSPORT_JSON", "phonons":"QE_PHONON_GAMMA", "qe_ph":"QE_PHONON_GAMMA", "raman":"QE_RAMAN", "qe_raman":"QE_RAMAN", "qe_polar_gamma":"QE_POLAR_GAMMA", "qe_dynmat":"QE_DYNMAT_POLAR", "qe_epsilon":"QE_EPSILON_TENSOR", "phonon_band_structure":"PHONON_DISPERSION_RAW_DATA"}
  # Manifest order is generated DAG order, so downstream Results can retain SCF scientific state.
  for task_id,task in manifest.items():
   runtime=record.tasks.get(task_id)
   if runtime is None or runtime.state is not TaskState.COMPLETED: continue
   semantic=str(task.get("semantic_task_type") or (task.get("metadata") or {}).get("semantic_task_type", "")); route=routes.get(semantic)
   task_metadata=task.get("metadata",{}) or {}
   purpose=(task_metadata.get("task_metadata",{}) or {}).get("purpose")
   if semantic in {"raman", "qe_raman"} and any(
    (candidate.get("semantic_task_type") or (candidate.get("metadata") or {}).get("semantic_task_type")) == "qe_dynmat"
    and ((candidate.get("metadata",{}).get("task_metadata",{}) or {}).get("purpose") == "raman")
    and task_id in tuple(candidate.get("dependencies",()) or ())
    for candidate in manifest.values()
   ):
    continue
   if task.get("calculation_id") == "qe_matdyn_dispersion": route="PHONON_DISPERSION_RAW_DATA"
   if semantic == "qe_ph" and ((task.get("metadata",{}).get("task_metadata",{}) or {}).get("purpose") == "harmonic_qmesh"): continue
   if route is None: continue
   source=self._source(root,task,runtime,semantic)
   if source is None:
    errors.append(f"{semantic}: declared result source is missing."); continue
   # Raman ph.x emits displacement tensors; QE dynmat emits the mode table.
   # Older completed Raman workflows predate the private dynmat manifest task,
   # so consume only the matching sibling artifacts in the same task directory.
   if semantic in {"raman", "qe_raman"}:
    directory=(root/str(task.get("working_directory", ""))).resolve()
    dynmat_source=next((candidate for candidate in (directory/"dynmat.out", directory/"raman.dynmat.out") if candidate.is_file()),None)
    if dynmat_source is not None:
     source=dynmat_source
     sibling=directory/"dynmat.stdout"
     parse_kwargs_extra={"activity_text": sibling.read_text(encoding="utf-8",errors="replace") if sibling.is_file() else "", "raman_tensor_text": Path(runtime.stdout_path).read_text(encoding="utf-8",errors="replace") if runtime is not None and runtime.stdout_path and Path(runtime.stdout_path).is_file() else ""}
    else:
     parse_kwargs_extra={}
   else:
    parse_kwargs_extra={}
   try:
    if semantic == "qe_dynmat" and purpose == "analytic_reference": continue
    if semantic == "qe_projwfc" and purpose == "orbital_character": route="ORBITAL_CHARACTER_RAW_DATA"
    parse_kwargs={"request_id":record.request_id,"execution_id":execution_id,"task_id":task_id,"method_metadata":task_metadata.get("electronic_method",{}),"execution_state":runtime.state.value,"return_code":runtime.return_code}; parse_kwargs.update(parse_kwargs_extra);
    if semantic == "qe_bader":
     field=((task.get("metadata") or {}).get("task_metadata") or {}).get("field",{})
     if not field:
      for parent_id in ancestors(task_id):
       parent_meta=manifest.get(parent_id,{}).get("metadata",{}) or {}
       field=((parent_meta.get("task_metadata") or {}).get("field",{}))
       if field: break
     atoms=field.get("atoms",[]) if isinstance(field,dict) else []
     parse_kwargs["species"]=[str(atom.get("element", "")) for atom in atoms if isinstance(atom,dict)]
     parse_kwargs["expected_atom_count"] = len(atoms)
     pseudo=(task.get("metadata") or {}).get("pseudopotentials", {})
     parse_kwargs["z_valence"]=[(pseudo.get(str(atom.get("element", "")), {}) or {}).get("z_valence") for atom in atoms if isinstance(atom,dict)]
    if semantic == "qe_lowdin":
     field=((task_metadata.get("task_metadata") or {}).get("field",{}))
     if not field:
      for parent_id in ancestors(task_id):
       parent_meta=manifest.get(parent_id,{}).get("metadata",{}) or {}; field=((parent_meta.get("task_metadata") or {}).get("field",{}))
       if field: break
     atoms=field.get("atoms",[]) if isinstance(field,dict) else []
     parse_kwargs["species"]=[str(atom.get("element", "")) for atom in atoms if isinstance(atom,dict)]
     parse_kwargs["expected_atom_count"]=len(atoms) if atoms else None
    if semantic == "qe_pp": parse_kwargs["field_metadata"]=((task_metadata.get("task_metadata") or {}).get("field",{}))
    if semantic in {"raman", "qe_raman"}:
     parse_kwargs["expected_mode_count"]=(task_metadata.get("expected_mode_count") or (task_metadata.get("task_metadata") or {}).get("expected_mode_count"))
     parse_kwargs["backend_version"]=(task_metadata.get("qe_version") or "7.6")
     parse_kwargs["functional"]=(task_metadata.get("electronic_method",{}) or {}).get("functional", "PZ")
     parse_kwargs["pseudopotentials"]=task_metadata.get("pseudopotentials",{})
     parse_kwargs["asr"]=(task_metadata.get("task_metadata",{}) or {}).get("asr", "crystal")
    if semantic in {"phonons", "qe_ph", "qe_polar_gamma"}:
     parse_kwargs["expected_mode_count"]=(task_metadata.get("expected_mode_count") or (task_metadata.get("task_metadata") or {}).get("expected_mode_count"))
     parse_kwargs["backend_version"]=(task_metadata.get("qe_version") or "7.6")
     parse_kwargs["fildyn"]=(Path(root) / str(task.get("working_directory", "")) / str(task_metadata.get("polar_fildyn", "polar_gamma") if semantic == "qe_polar_gamma" else task_metadata.get("qe_prefix", "qs") + ".dyn")).as_posix()
     parse_kwargs["electronic_method"]=task_metadata.get("electronic_method", {})
     parse_kwargs["pseudopotentials"]=task_metadata.get("pseudopotentials", {})
     if semantic == "qe_polar_gamma":
      atoms=(record.__dict__.get("structure") or {}).get("atoms", []) if isinstance(record.__dict__.get("structure"), dict) else []
      parse_kwargs["expected_atom_count"] = len(atoms)
      parse_kwargs["atom_elements"] = [str(atom.get("element", "")) for atom in atoms if isinstance(atom, dict)] or list((task_metadata.get("task_metadata", {}) or {}).get("atom_elements", ()))
      method=task_metadata.get("electronic_method", {}) or {}
      parse_kwargs["functional"] = method.get("functional", method.get("xc_functional", "PBE"))
      parse_kwargs["spin_treatment"] = method.get("spin_treatment", "SCALAR_NONSPIN")
    if semantic == "qe_matdyn":
     mat_meta=task_metadata.get("task_metadata", {}) or {}
     parse_kwargs["q_mesh"]=mat_meta.get("qmesh")
     parse_kwargs["asr"]=mat_meta.get("asr", "crystal")
     parse_kwargs["branch_count"]=(mat_meta.get("expected_mode_count") or (3 * len((record.__dict__.get("structure") or {}).get("atoms", ())) if isinstance(record.__dict__.get("structure"), dict) else None)); parse_kwargs["expected_mode_count"]=mat_meta.get("expected_mode_count")
     parse_kwargs["cell_A"]=mat_meta.get("cell_A")
     parse_kwargs["high_symmetry_labels"]=mat_meta.get("high_symmetry_labels", [])
     parse_kwargs["high_symmetry_indices"]=mat_meta.get("high_symmetry_indices", [])
    if semantic == "qe_dynmat":
     dyn_meta=task_metadata.get("task_metadata", {}) or {}
     if purpose == "phonon_dielectric": route="QE_DYNMAT_PHONON_DIELECTRIC"
     if purpose == "raman": route="QE_RAMAN"
     parse_kwargs.update({"purpose":purpose,"direction":dyn_meta.get("direction_unit_cartesian", [1.,0.,0.]),"original_direction":dyn_meta.get("original_requested_direction", dyn_meta.get("direction_unit_cartesian", [1.,0.,0.])), "asr":dyn_meta.get("asr", "crystal"),"expected_mode_count":dyn_meta.get("expected_mode_count"),"backend_version":task_metadata.get("qe_version", "7.6")})
     if purpose == "raman":
      parse_kwargs["pseudopotentials"]=task_metadata.get("pseudopotentials",{})
      parse_kwargs["calculation_settings"]=_raman_calculation_settings(root,manifest,ancestors(task_id),task)
      parse_kwargs["tool_id"]="dynmat.x"
     parent_id=(dyn_meta.get("parent_raman_task_id") if purpose == "raman" else dyn_meta.get("parent_polar_task_id"))
     parent_task=manifest.get(parent_id, {}) if parent_id else {}
     reference=analytic_references.get(parent_id)
     if reference is not None:
      parse_kwargs["uncorrected_frequencies_cm1"]=reference["frequencies_cm1"]
      parse_kwargs["uncorrected_frequencies_THz"]=reference["frequencies_THz"]
      parse_kwargs["uncorrected_reference"]="ASR-consistent analytic dynmat reference"
     parent_runtime=record.tasks.get(parent_id) if parent_id else None
     if parent_runtime is not None and parent_runtime.stdout_path:
      parent_stdout=Path(parent_runtime.stdout_path)
      if parent_stdout.is_file():
       parent_text=parent_stdout.read_text(encoding="utf-8", errors="replace")
       number=r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"
       rows=re.findall(r"freq\s*\(\s*(\d+)\s*\)\s*=\s*("+number+r")\s*\[THz\]\s*=\s*("+number+r")\s*\[cm-1\]", parent_text, re.I)
       if rows and reference is None:
        parse_kwargs["uncorrected_frequencies_THz"]=[float(item[1].replace("D","E").replace("d","e")) for item in rows]
        parse_kwargs["uncorrected_frequencies_cm1"]=[float(item[2].replace("D","E").replace("d","e")) for item in rows]
       parse_kwargs["activity_text"]=parent_text
       if purpose == "raman": parse_kwargs["raman_tensor_text"]=parent_text
     parse_kwargs["polar_artifact_provenance"]={"parent_task_id":parent_id,"parent_working_directory":parent_task.get("working_directory")}
     if runtime.stdout_path and Path(runtime.stdout_path).is_file():
      parse_kwargs["activity_text"]=Path(runtime.stdout_path).read_text(encoding="utf-8", errors="replace")
    if semantic == "qe_bands": parse_kwargs["band_path"]=(task.get("metadata") or {}).get("band_path");
    if semantic == "qe_epsilon":
     parse_kwargs["optical_settings"]=(task_metadata.get("task_metadata",{}) or {}).get("optical_settings", {})
     parse_kwargs["qe_prefix"]=task_metadata.get("qe_prefix", "")
    if semantic == "epw_run":
     candidates=sorted((Path(root) / str(task.get("working_directory", ""))).resolve().glob("*.a2f.*"))
     if len(candidates) != 1: raise ResultParseError("EPW alpha2F series selection is ambiguous or missing.")
     parse_kwargs["a2f_path"]=str(candidates[0])
    result=DEFAULT_PARSERS.parse(route,source,**parse_kwargs)
    result.metadata.setdefault("electronic_method",(task.get("metadata") or {}).get("electronic_method",{}))
    if semantic == "qe_polar_gamma" and result.result_type == "BornEffectiveChargeResult":
     epsilon = np.asarray(result.metadata.get("epsilon_infinity"), dtype=float) if result.metadata.get("epsilon_infinity") is not None else None
     if epsilon is None:
      # The parser keeps epsilon in metadata and the separate result below makes
      # the shared private tensor discoverable without conflating it with BEC.
      epsilon_node = None
      import xml.etree.ElementTree as ET
      tree=ET.parse(source); epsilon_node=tree.getroot().find('.//EPSILON')
      epsilon=np.asarray([float(x) for x in (epsilon_node.text or '').split()],float).reshape(3,3)
     dielectric=ScientificResult("PolarElectronicDielectricResult",ResultStatus.VALID,result.provenance,arrays={"epsilon_infinity":epsilon,"symmetry_residual":epsilon-epsilon.T},metadata={"units":{"epsilon_infinity":"dimensionless"},"definition":"electronic high-frequency dielectric tensor epsilon_infinity","backend":"Quantum ESPRESSO","backend_version":result.metadata.get("backend_version","7.6"),"functional":result.metadata.get("functional","PBE"),"spin_treatment":result.metadata.get("spin_treatment","SCALAR_NONSPIN"),"symmetry_residual_norm":float(np.linalg.norm(epsilon-epsilon.T)),"source_bec_result_id":result.result_id})
     store.save(dielectric); parsed.append(dielectric.result_id)

    lineage=ancestors(task_id)
    if result.result_type == "OrbitalCharacterResult":
     parent_band=next((parsed_by_task[parent] for parent in lineage if parent in parsed_by_task and parsed_by_task[parent].result_type == "BandStructureResult"), None)
     if parent_band is not None:
      kcoords=np.asarray(parent_band.arrays.get("path_coordinate",()),dtype=float); energies=np.asarray(parent_band.arrays.get("energies",()),dtype=float)
      if energies.ndim == 2 and len(kcoords):
       ki=np.asarray(result.arrays.get("k_index",()),dtype=int)-1; bi=np.asarray(result.arrays.get("band_index",()),dtype=int)-1
       if len(ki) and np.all((ki>=0)&(ki<len(kcoords))) and np.all((bi>=0)&(bi<energies.shape[1])):
        result.arrays["k_distance"]=kcoords[ki]; result.arrays["energy_eV"]=energies[ki,bi]; result.metadata["source_band_result_id"]=parent_band.result_id
    result.metadata.setdefault("workflow_provenance",{"terminal_task_id":task_id,"terminal_semantic_task":semantic,"parent_task_ids":list(task.get("dependencies",())) if isinstance(task.get("dependencies",()),(list,tuple)) else [],"ancestor_task_ids":list(lineage),"purpose":(task_metadata.get("task_metadata",{}) or {}).get("purpose"),"structure_fingerprint":task_metadata.get("structure_fingerprint",""),"pseudopotentials":task_metadata.get("pseudopotentials",{}),"qe_prefix":task_metadata.get("qe_prefix"),"qe_outdir":task_metadata.get("qe_outdir"),"task_parameter_signatures":{parent:(manifest.get(parent,{}).get("metadata",{}) or {}).get("parameter_signature") for parent in (*lineage,task_id)}})
    if semantic in {"qe_dos","qe_projwfc"} and route in {"DOS_RAW_DATA","PDOS_RAW_DATA"}:
     upstream=[parsed_by_task[parent] for parent in lineage if manifest.get(parent,{}).get("calculation_id")=="scf" and parent in parsed_by_task]
     # The terminal dos.x header wins. Otherwise use only the parent SCF Result,
     # never an unrelated prior execution or a sibling public calculation.
     if "fermi_energy_eV" not in result.metadata:
      parent_fermi=next((item.scalars.get("fermi_energy",{}).get("value") for item in upstream if isinstance(item.scalars.get("fermi_energy"),dict) and item.scalars["fermi_energy"].get("value") is not None),None)
      if parent_fermi is not None:
       result.metadata["fermi_energy_eV"]=float(parent_fermi)
       result.metadata["fermi_reference"]={"source":"parent SCF GroundStateResult","source_task":next(item.provenance.source_task_id for item in upstream if isinstance(item.scalars.get("fermi_energy"),dict) and item.scalars["fermi_energy"].get("value") is not None),"value_eV":float(parent_fermi)}
       result.metadata.setdefault("energy_reference",{})["display_default"]="Fermi = 0"
     if any(item.status is ResultStatus.NOT_CONVERGED for item in upstream):
      result.status=ResultStatus.NOT_CONVERGED
      result.warnings.append("The parent SCF execution completed but did not scientifically converge.")
    if result.result_type == "OpticalDielectricResult":
     from backend.results.optical import derive_optical_properties
     derived=derive_optical_properties(result)
     if reparse or derived.result_id not in store.list(): store.save(derived)
     parsed.append(derived.result_id)
    if semantic == "qe_pp" and (task_metadata.get("task_metadata",{}) or {}).get("purpose") == "work_function":
     from backend.analyze.work_function import derive_work_function
     parents=[parsed_by_task[parent] for parent in lineage if manifest.get(parent,{}).get("calculation_id")=="scf" and parent in parsed_by_task]
     if parents:
      field=((task_metadata.get("task_metadata",{}) or {}).get("field") or {})
      settings=(task_metadata.get("task_metadata",{}) or {}).get("analysis",{})
      analysis=derive_work_function(result,parents[0],field.get("atoms",[]),axis_override=settings.get("surface_normal"),window_A=settings.get("macro_window_A"))
      payload={key:value for key,value in analysis.items() if key not in {"profile","macroscopic_eV","vacuum_levels"}}
      payload["vacuum_levels"]=[item.__dict__ for item in analysis.get("vacuum_levels",[])]
      derived=ScientificResult("WorkFunctionResult",analysis["status"],result.provenance,scalars={"fermi_energy":{"value":analysis.get("fermi_energy_eV"),"unit":"eV"}} if analysis.get("fermi_energy_eV") is not None else {},arrays={key:value for key,value in {"distance_A":analysis.get("profile",{}).get("distance_A"),"potential_raw_Ry":analysis.get("profile",{}).get("potential_raw_Ry"),"potential_eV":analysis.get("profile",{}).get("potential_eV"),"macroscopic_eV":analysis.get("macroscopic_eV")} .items() if value is not None},metadata={"work_function_analysis":payload,"source_potential_result_id":result.result_id},warnings=list(analysis.get("diagnostics",[])))
      store.save(derived); parsed.append(derived.result_id)
    if reparse or result.result_id not in store.list(): store.save(result)
    if semantic == "qe_bands" and (task_metadata.get("task_metadata",{}) or {}).get("purpose") in {"band_gap", "effective_mass"}:
     # Public derived workflows share the signed bands terminal without making
     # ordinary Band Structure requests emit surprise auxiliary Results.
     derived_values=(derive_band_gap(result),) if (task_metadata.get("task_metadata",{}) or {}).get("purpose") == "band_gap" else (derive_effective_mass(result, carrier="electron"),)
     for derived in derived_values:
      if reparse or derived.result_id not in store.list(): store.save(derived)
      parsed.append(derived.result_id)
    if result.result_type == "LowdinPopulationResult" and purpose == "magnetic_moment":
     parent=next((parsed_by_task[parent] for parent in lineage if parsed_by_task.get(parent) is not None and parsed_by_task[parent].result_type == "GroundStateResult"),None)
     derived=derive_magnetic_moments(result,parent)
     if reparse or derived.result_id not in store.list(): store.save(derived)
     parsed.append(derived.result_id)
    if result.result_type == "BaderChargeResult" and (task_metadata.get("task_metadata", {}) or {}).get("purpose") == "charge_transfer":
     derived=derive_charge_transfer(result)
     if reparse or derived.result_id not in store.list(): store.save(derived)
     parsed.append(derived.result_id)
    parsed_by_task[task_id]=result
    parsed.append(result.result_id)
   except (ResultParseError,ResultStoreError,ValueError) as error:
    errors.append(f"{semantic}: {error}")
  return {"parsed":tuple(parsed),"errors":tuple(errors),"rows":self.summaries(root,execution_id)}
