"""Qt-free Calculate-facing access to C8 execution-sidecar Results."""
from __future__ import annotations
import json
import numpy as np
from pathlib import Path
from backend.execution import ExecutionStore
from backend.execution.models import TaskState
from backend.results import DEFAULT_PARSERS, ResultStore, ResultStoreError, ResultParseError, ResultStatus
from backend.results.models import ScientificResult
from backend.results.derived import derive_band_gap, derive_effective_mass, derive_charge_transfer, derive_magnetic_moments


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
  names={"qe_bands":("bands.dat",), "qe_fs":("fermi_surface.bxsf","*_fs.bxsf","*.bxsf"), "qe_dos":("dos.dat",), "qe_matdyn":("phdos.dat","phonon.dos"), "qe_projwfc":("*.pdos_atm#*","pdos_atm#*","*.projwfc_up"), "qe_pp":(), "qe_bader":("ACF.dat",)}
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
  parsed=[]; errors=[]
  parsed_by_task={}
  def ancestors(task_id):
   seen=set(); stack=list(manifest.get(task_id,{}).get("dependencies",()) or ())
   while stack:
    parent=str(stack.pop())
    if parent in seen: continue
    seen.add(parent); stack.extend(manifest.get(parent,{}).get("dependencies",()) or ())
   return tuple(sorted(seen))
  routes={"scf":"QE_SCF_STDOUT","relax":"QE_RELAX_STDOUT","vc_relax":"QE_RELAX_STDOUT","qe_bands":"BAND_STRUCTURE_RAW_DATA","qe_fs":"FERMI_SURFACE_BXSF","qe_bader":"BADER_ACF","qe_lowdin":"LOWDIN_POPULATION","qe_hp":"HUBBARD_PARAMETER_RAW_DATA","qe_dos":"DOS_RAW_DATA","qe_matdyn":"PHONON_DOS_RAW_DATA","qe_projwfc":"PDOS_RAW_DATA","qe_pp":"VOLUMETRIC_RAW_DATA","wannier90_run":"WANNIER_WOUT","epw":"EPW_SUMMARY"}
  # Manifest order is generated DAG order, so downstream Results can retain SCF scientific state.
  for task_id,task in manifest.items():
   runtime=record.tasks.get(task_id)
   if runtime is None or runtime.state is not TaskState.COMPLETED: continue
   semantic=str(task.get("semantic_task_type") or (task.get("metadata") or {}).get("semantic_task_type", "")); route=routes.get(semantic)
   if route is None: continue
   source=self._source(root,task,runtime,semantic)
   if source is None:
    errors.append(f"{semantic}: declared result source is missing."); continue
   try:
    task_metadata=task.get("metadata",{}) or {}
    purpose=(task_metadata.get("task_metadata",{}) or {}).get("purpose")
    if semantic == "qe_projwfc" and purpose == "orbital_character": route="ORBITAL_CHARACTER_RAW_DATA"
    parse_kwargs={"request_id":record.request_id,"execution_id":execution_id,"task_id":task_id,"method_metadata":task_metadata.get("electronic_method",{})};
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
    if semantic == "qe_bands": parse_kwargs["band_path"]=(task.get("metadata") or {}).get("band_path");
    result=DEFAULT_PARSERS.parse(route,source,**parse_kwargs)
    result.metadata.setdefault("electronic_method",(task.get("metadata") or {}).get("electronic_method",{}))
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
