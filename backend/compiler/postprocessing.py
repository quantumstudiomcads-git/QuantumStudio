"""C8A QE post-processing expansion; raw artifacts only."""
from __future__ import annotations
import hashlib, json
from backend.compiler.execution_plan import PlannedTask
from backend.engines.qe.models import InvalidQEParameterError

def _sig(value): return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()[:16]

def _path(value, label):
    if not isinstance(value, list) or len(value) < 2: raise InvalidQEParameterError(f"{label} requires an explicit ordered path with at least two points.")
    points=[]
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("coordinates"), (list,tuple)) or len(item["coordinates"]) != 3: raise InvalidQEParameterError(f"{label} points require three fractional coordinates.")
        count=int(item.get("points", 0))
        if count < 1: raise InvalidQEParameterError(f"{label} points require positive interpolation counts.")
        points.append({"label":str(item.get("label","")),"coordinates":[float(x) for x in item["coordinates"]],"points":count})
    return points

def expand(request, tasks, parameters):
    selected=set(request.selected_calculations); by={task.calculation_id:task for task in tasks}; scf=by.get("scf")
    if not scf: return tasks
    result=[task for task in tasks if task.calculation_id not in {"bands","dos","pdos","charge_density","spin_density","phonon_dos"}]
    def add(name, semantic, tool, deps, params, inputs, outputs, metadata=None):
        signature=_sig({"semantic":semantic,"parameters":params}); task=PlannedTask(id=f"{request.id}:{semantic}:{signature}",calculation_id=name,semantic_task_type=semantic,engine_id="quantum_espresso",tool_id=tool,parameter_signature=signature,depends_on_task_ids=tuple(dep.id for dep in deps),parameters=params,structure_reference="request_snapshot",artifact_inputs=tuple(inputs),artifact_outputs=tuple(outputs),metadata=metadata or {}); result.append(task); return task
    if "bands" in selected:
        values=dict(parameters["bands"]); path=_path(values.get("kpath"),"Band structure")
        pw=add("qe_pw_bands","qe_pw_bands","pw.x",[scf],{**values,"band_path":path},["qe_save"],["qe_band_eigenvalues"],{"purpose":"bands"})
        add("qe_bands","qe_bands","bands.x",[pw],{"filband":"bands.dat"},["qe_save","qe_band_eigenvalues"],["BAND_STRUCTURE_RAW_DATA"])
    for public, terminal, tool, output in (("dos","qe_dos","dos.x","DOS_RAW_DATA"),("pdos","qe_projwfc","projwfc.x","PDOS_RAW_DATA")):
        if public in selected:
            values=dict(parameters[public]); mesh=values.get("dense_kpoints");
            if not isinstance(mesh,(list,tuple)) or len(mesh)!=3: raise InvalidQEParameterError(f"{public} requires dense_kpoints mesh.")
            nscf=add(f"qe_pw_nscf_{public}","qe_pw_nscf","pw.x",[scf],{**values,"kpoints":{"mode":"automatic","mesh":list(mesh),"shifts":[0,0,0]},"occupations":"tetrahedra"},["qe_save"],["qe_wavefunctions","qe_eigenvalues"],{"purpose":public})
            add(terminal,terminal,tool,[nscf],values,["qe_save","qe_wavefunctions"],[output],{"purpose":public})
    for public, kind, output in (("charge_density","charge","CHARGE_DENSITY_RAW_DATA"),("spin_density","spin","SPIN_DENSITY_RAW_DATA")):
        if public in selected:
            values=dict(parameters[public])
            if kind=="spin" and not values.get("spin"): raise InvalidQEParameterError("Spin density requires spin-polarized QE settings.")
            add("qe_pp","qe_pp","pp.x",[scf],{"plot_kind":kind},["qe_save"],[output],{"purpose":kind})
    if "phonon_dos" in selected:
        ph=by.get("phonons")
        if ph is None: raise InvalidQEParameterError("phonon_dos requires phonons.")
        result=[task for task in result if task is not ph]
        ph=add("qe_ph","qe_ph","ph.x",[scf],parameters["phonons"],["qe_save"],["QE_DYNAMICAL_MATRIX"])
        q2r=add("qe_q2r","qe_q2r","q2r.x",[ph],{"fildyn":"dynamical-matrix","flfrc":"force_constants","zasr":"simple"},["QE_DYNAMICAL_MATRIX"],["FORCE_CONSTANTS"])
        add("qe_matdyn_dos","qe_matdyn","matdyn.x",[q2r],{"mode":"dos","mesh":parameters["phonon_dos"].get("qmesh") or parameters["phonons"].get("qmesh")},["FORCE_CONSTANTS"],["PHONON_DOS_RAW_DATA"])
    return result
